"""Cedar authorization, backed by the real Cedar 4.x engine via cedarpy.

Three things about this adapter are worth knowing before you change it.

**1. Policy ids are positional.** Cedar's diagnostics report POSITIONAL policy ids
(`policy0`, `policy1`, ...), not the `@id("...")` annotation. Mapping a denial to a human
sentence therefore needs an extra step: at load time we parse the policy set to JSON, read
each policy's annotations, and build positional-id -> annotation. Without that, "@id turns a
denial into a sentence" simply does not work, and you get `policy6` on screen.

**2. The request carries a context.** Cedar core has no clock, so consent expiry is decided
by comparing `resource.expiresAt` against `context.now`, both epoch SECONDS. The comparison
lives in the policy, not here: this adapter forwards the instant and makes no judgement
about it. `now` is required for every action, so there is no code path on which a
time-sensitive rule silently evaluates against a missing value.

**3. Everything that is not a decision is AuthorizationUnavailable.** An unknown action, an
unknown resource type, a blank principal id, a missing `now`, or a Cedar evaluation error
all raise rather than returning `allowed=False`. That distinction matters: a denial is a
sentence to show a user, while an unavailable authorization boundary is an outage, and the
two must not be reported as the same thing. Both fail closed -- neither permits.

The known action and entity-type vocabularies are read from the schema rather than retyped
here, so the schema is the single source of truth and a policy for a type that does not
exist cannot be added without the schema changing too.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cedarpy import Decision, is_authorized, policies_to_json_str, validate_policies

from aadesh_core.domain import Principal
from aadesh_core.errors import AuthorizationUnavailable
from aadesh_core.ports.authz import AuthorizationDecision, AuthzResource, EntityRef

NAMESPACE = "Aadesh"
PRINCIPAL_TYPE = f"{NAMESPACE}::Principal"
DEFAULT_DENIAL_KEY = "_default"


def _uid(entity_type: str, entity_id: str) -> dict[str, str]:
    return {"type": f"{NAMESPACE}::{entity_type}", "id": entity_id}


def _attr_value(value: Any) -> Any:
    if isinstance(value, EntityRef):
        return {"__entity": _uid(value.entity_type, value.entity_id)}
    return value


class CedarAuthorizationProvider:
    """Evaluates infra/cedar/policies.cedar in-process. No network, no Docker."""

    def __init__(
        self,
        *,
        policy_path: Path,
        denials_path: Path,
        schema_path: Path | None = None,
    ) -> None:
        """Load the policy set, or refuse to exist.

        Everything here is wrapped so that a missing file, an unreadable one, a syntax error in
        the policies, or malformed denial copy surfaces as `AuthorizationUnavailable` rather
        than as `FileNotFoundError`, `JSONDecodeError` or a Cedar parse fault.

        That is not cosmetic. A boundary that fails to LOAD is an outage exactly as much as one
        that fails to EVALUATE, and callers already handle `AuthorizationUnavailable` by
        refusing the request. An untyped exception escapes whatever handling exists and depends
        on a process supervisor to turn it into a refusal -- which is a lot of trust to place in
        a crash being noticed. Half a policy set is worse still: the forbids that failed to
        parse are precisely the ones whose absence nobody would see.
        """
        try:
            self._policies = Path(policy_path).read_text(encoding="utf-8")
            self._denials: dict[str, str] = json.loads(
                Path(denials_path).read_text(encoding="utf-8")
            )
            self._schema = Path(schema_path).read_text(encoding="utf-8") if schema_path else None
            self._annotations = self._build_annotation_map()
            self._known_actions, self._known_entity_types = self._build_vocabularies()
        except AuthorizationUnavailable:
            raise
        except Exception as exc:
            raise AuthorizationUnavailable(
                f"Authorization policy set could not be loaded from {policy_path}: {exc}"
            ) from exc

    # -- policy metadata ----------------------------------------------------

    def _build_annotation_map(self) -> dict[str, str]:
        """positional policy id -> @id annotation, plus a record of which are forbids."""
        parsed = json.loads(policies_to_json_str(self._policies))
        mapping: dict[str, str] = {}
        self._forbid_annotations: list[str] = []
        for policy_id, body in parsed.get("staticPolicies", {}).items():
            annotation = (body.get("annotations") or {}).get("id")
            if annotation:
                mapping[policy_id] = annotation
                if body.get("effect") == "forbid":
                    self._forbid_annotations.append(annotation)
        return mapping

    def _build_vocabularies(self) -> tuple[frozenset[str], frozenset[str]]:
        """The action and entity-type names the schema declares.

        Empty when no schema is configured, which disables the pre-check and leaves Cedar to
        refuse the request on its own terms. That is still fail-closed: an action no policy
        matches is denied, and an unresolvable entity raises.
        """
        if self._schema is None:
            return frozenset(), frozenset()

        schema = json.loads(self._schema)
        declared = schema.get(NAMESPACE, {})
        actions = frozenset((declared.get("actions") or {}).keys())
        entity_types = frozenset((declared.get("entityTypes") or {}).keys())
        return actions, entity_types

    @property
    def forbid_annotations(self) -> list[str]:
        """@id annotations of every forbid policy, so tests can assert denial copy exists."""
        return list(self._forbid_annotations)

    @property
    def known_actions(self) -> frozenset[str]:
        return self._known_actions

    def validate(self) -> list[str]:
        """Typecheck the policies against the schema. Returns a list of error strings."""
        if self._schema is None:
            return []
        result = validate_policies(self._policies, self._schema)
        if result.validation_passed:
            return []
        return [f"{e.policy_id}: {e.error}" for e in result.errors]

    # -- request well-formedness --------------------------------------------

    def _require_well_formed(
        self, *, principal: Principal, action: str, resource: AuthzResource, context: Mapping
    ) -> None:
        """Refuse to ask Cedar a question it cannot answer, before asking it.

        Each check below corresponds to a way a request could arrive malformed from a handler
        that failed to build it properly. Raising here rather than letting Cedar deny means
        the caller can tell "this person may not do this" apart from "this request was never
        answerable", which is the difference between a 403 and an outage.
        """
        if not isinstance(principal, Principal) or not str(principal.principal_id).strip():
            raise AuthorizationUnavailable(
                "Authorization requires a principal with a non-empty principal_id."
            )
        if not str(principal.role).strip():
            raise AuthorizationUnavailable(
                f"Authorization requires a role. Principal {principal.principal_id!r} has none."
            )
        if not str(action).strip():
            raise AuthorizationUnavailable("Authorization requires a non-empty action.")

        if self._known_actions and action not in self._known_actions:
            raise AuthorizationUnavailable(
                f"Unknown action {action!r}. The schema declares: {sorted(self._known_actions)}."
            )
        if not isinstance(resource, AuthzResource) or not str(resource.entity_id).strip():
            raise AuthorizationUnavailable(
                "Authorization requires a resource with a non-empty entity_id."
            )
        if self._known_entity_types and resource.entity_type not in self._known_entity_types:
            raise AuthorizationUnavailable(
                f"Unknown resource type {resource.entity_type!r}. The schema declares: "
                f"{sorted(self._known_entity_types)}."
            )

        # `now` is required of every action, so a time-sensitive rule can never evaluate
        # against a missing instant. A bool is rejected explicitly: `True` is an int in
        # Python, and silently accepting it would put the epoch at 1970.
        now = (context or {}).get("now")
        if not isinstance(now, int) or isinstance(now, bool):
            raise AuthorizationUnavailable(
                f"Authorization context must carry an integer `now` (epoch seconds); got "
                f"{now!r}. Consent expiry and revocation are decided by comparing against it, "
                f"so a request without one is not answerable."
            )

    # -- the port -----------------------------------------------------------

    def _entities(self, principal: Principal, resource: AuthzResource) -> list[dict]:
        principal_attrs: dict[str, Any] = {"role": principal.role}
        if principal.assigned_site is not None:
            principal_attrs["assignedSite"] = principal.assigned_site

        entities: list[dict] = [
            {
                "uid": _uid("Principal", principal.principal_id),
                "attrs": principal_attrs,
                "parents": [],
            },
            {
                "uid": _uid(resource.entity_type, resource.entity_id),
                "attrs": {k: _attr_value(v) for k, v in resource.attributes.items()},
                "parents": [],
            },
        ]

        # Any entity referenced by an attribute must exist in the store, otherwise Cedar
        # cannot evaluate `resource.worker == principal`.
        known = {json.dumps(e["uid"], sort_keys=True) for e in entities}
        for value in resource.attributes.values():
            if not isinstance(value, EntityRef):
                continue
            uid = _uid(value.entity_type, value.entity_id)
            key = json.dumps(uid, sort_keys=True)
            if key not in known:
                entities.append({"uid": uid, "attrs": {}, "parents": []})
                known.add(key)
        return entities

    def _reason(self, policy_ids: list[str]) -> tuple[str | None, str]:
        for policy_id in policy_ids:
            annotation = self._annotations.get(policy_id)
            if annotation and annotation in self._denials:
                return annotation, self._denials[annotation]
        return None, self._denials.get(
            DEFAULT_DENIAL_KEY, "Cedar denied this: no policy permits that action."
        )

    def authorize(
        self,
        *,
        principal: Principal,
        action: str,
        resource: AuthzResource,
        context: Mapping[str, Any] | None = None,
    ) -> AuthorizationDecision:
        request_context = dict(context or {})
        self._require_well_formed(
            principal=principal, action=action, resource=resource, context=request_context
        )

        request = {
            "principal": f'{PRINCIPAL_TYPE}::"{principal.principal_id}"',
            "action": f'{NAMESPACE}::Action::"{action}"',
            "resource": (f'{NAMESPACE}::{resource.entity_type}::"{resource.entity_id}"'),
            "context": request_context,
        }

        try:
            result = is_authorized(
                request, self._policies, json.dumps(self._entities(principal, resource))
            )
        except Exception as exc:
            raise AuthorizationUnavailable(
                f"Cedar could not reach a decision for {action} on "
                f"{resource.entity_type}::{resource.entity_id}: {exc}"
            ) from exc

        reasons = list(result.diagnostics.reasons or [])

        if result.decision == Decision.Allow:
            return AuthorizationDecision(
                allowed=True,
                policy_id=next(
                    (self._annotations[r] for r in reasons if r in self._annotations), None
                ),
                reason=f"Permitted: {action} on {resource.entity_type}.",
            )

        policy_id, sentence = self._reason(reasons)
        return AuthorizationDecision(allowed=False, policy_id=policy_id, reason=sentence)

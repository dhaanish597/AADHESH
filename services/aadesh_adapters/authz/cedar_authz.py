"""Cedar authorization, backed by the real Cedar 4.x engine via cedarpy.

Implementation note worth knowing before you change anything here. Cedar's diagnostics report
POSITIONAL policy ids (`policy0`, `policy1`, ...), not the `@id("...")` annotation. Mapping a
denial to a human sentence therefore needs an extra step: at load time we parse the policy set
to JSON, read each policy's annotations, and build positional-id -> annotation. Without that,
"@id turns a denial into a sentence" simply does not work, and you get `policy6` on screen.
"""

from __future__ import annotations

import json
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
        self._policies = Path(policy_path).read_text(encoding="utf-8")
        self._denials: dict[str, str] = json.loads(Path(denials_path).read_text(encoding="utf-8"))
        self._schema = Path(schema_path).read_text(encoding="utf-8") if schema_path else None
        self._annotations = self._build_annotation_map()

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

    @property
    def forbid_annotations(self) -> list[str]:
        """@id annotations of every forbid policy, so tests can assert denial copy exists."""
        return list(self._forbid_annotations)

    def validate(self) -> list[str]:
        """Typecheck the policies against the schema. Returns a list of error strings."""
        if self._schema is None:
            return []
        result = validate_policies(self._policies, self._schema)
        if result.validation_passed:
            return []
        return [f"{e.policy_id}: {e.error}" for e in result.errors]

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
        self, *, principal: Principal, action: str, resource: AuthzResource
    ) -> AuthorizationDecision:
        request = {
            "principal": f'{PRINCIPAL_TYPE}::"{principal.principal_id}"',
            "action": f'{NAMESPACE}::Action::"{action}"',
            "resource": (f'{NAMESPACE}::{resource.entity_type}::"{resource.entity_id}"'),
            "context": {},
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

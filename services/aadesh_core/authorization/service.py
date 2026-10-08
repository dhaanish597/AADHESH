"""The authorization boundary: the ONE place a request becomes a domain operation.

Every other module in the core is a library. This one is a gate, and the difference matters:
a library can be called from anywhere, so "remember to authorize first" is a convention that
survives until the first handler written in a hurry. Here, authorizing and acting are a single
call, so there is no ordering for a caller to get wrong.

    handler  ->  AuthorizationService  ->  [ Cedar ]  ->  domain operation
                        |                                   |
                   refuses here                        refuses here too

THE TWO REFUSALS ARE NOT REDUNDANT, AND THAT IS THE POINT
---------------------------------------------------------
The domain keeps its own identity rule (`parchi.acknowledge` refuses an actor who is not the
worker named on the record). This layer does not replace it, does not weaken it, and does not
pretend to own it. `tests/unit/test_authorization_boundary.py::test_13` swaps this layer's
provider for one that permits EVERYTHING and asserts the domain still refuses -- because a
security property enforced in exactly one place is one policy edit away from not being
enforced at all.

WHAT THIS LAYER IS NOT
----------------------
It is not a state machine. Cedar is asked "may this principal do this?" and never "is this
transition legal?". A sealed parchi is refused by `aadesh_core.parchi`, and the test of that
fact asserts that Cedar still says yes when asked. Adding `resource.state` checks here would
create a second state machine that would eventually disagree with the first.

It is not the legal decision engine either. Nothing here reads an AQI, a GRAP stage, or the
corpus.

FAIL CLOSED
-----------
`_authorize` has no `except` clause. If the provider raises `AuthorizationUnavailable` -- an
unloaded policy set, an engine fault, a missing request context -- that exception reaches the
caller and nothing is performed. There is deliberately no `try/except: return allowed=True`
shape anywhere in this file, and `tests/unit/test_authorization_no_bypass.py` fails the build
if one is ever added.
"""

from __future__ import annotations

from datetime import datetime

from aadesh_core.authorization.resources import (
    claim_assistance_resource,
    parchi_resource,
    site_resource,
    to_epoch_seconds,
)
from aadesh_core.consent import ClaimAssistanceContext
from aadesh_core.domain import Principal
from aadesh_core.errors import AuthorizationDenied
from aadesh_core.parchi import Parchi
from aadesh_core.parchi_ack.service import (
    AcknowledgementOutcome,
    acknowledge_parchi,
    resolve_parchi_for_payload,
)
from aadesh_core.ports.audit import AuditLog
from aadesh_core.ports.authz import AuthorizationDecision, AuthorizationProvider, AuthzResource
from aadesh_core.ports.parchi_ack import (
    AcknowledgementTokenStore,
    IdempotencyLedger,
    ParchiAckStore,
)

#: The actions this boundary mediates. Named as constants so a typo is a NameError at import
#: rather than an unknown-action string that the adapter would (correctly) refuse at runtime.
ISSUE_HALT = "IssueHalt"
VIEW_SITE_EXECUTION = "ViewSiteExecution"
ACKNOWLEDGE_OWN_PARCHI = "AcknowledgeOwnParchi"
VIEW_PARCHI = "ViewParchi"
ASSIST_CLAIM = "AssistClaim"


class AuthorizationService:
    """Authorize, then act -- as one step.

    Handlers depend on this, never on the domain module directly. The domain remains callable
    (Prompt 5's tests and the demo CLI call it), which is what makes the defence-in-depth claim
    checkable: the second lock is real and can be tested on its own.
    """

    def __init__(self, *, authz: AuthorizationProvider) -> None:
        self._authz = authz

    # -- the gate ----------------------------------------------------------------

    def _authorize(
        self,
        *,
        principal: Principal,
        action: str,
        resource: AuthzResource,
        now: datetime,
    ) -> AuthorizationDecision:
        """Ask, and turn a refusal into an exception.

        `now` is always supplied. A policy that compares a consent window against a missing
        instant would be evaluating a time-sensitive rule against nothing; the adapter raises
        `AuthorizationUnavailable` for an absent or non-integer `now` rather than defaulting it.
        """
        decision = self._authz.authorize(
            principal=principal,
            action=action,
            resource=resource,
            context={"now": to_epoch_seconds(now)},
        )
        if not decision.allowed:
            raise AuthorizationDenied(decision)
        return decision

    # -- site-scoped actions -----------------------------------------------------

    def require_issue_halt(
        self, *, principal: Principal, site_id: str, now: datetime
    ) -> AuthorizationDecision:
        """A supervisor may halt the site they are assigned to, and no other.

        The site is the RESOURCE, and the principal's assignment is an attribute of the
        principal -- so the check is "does this principal's site equal this resource's site",
        not "is this principal a supervisor". A role alone confers nothing here.
        """
        return self._authorize(
            principal=principal,
            action=ISSUE_HALT,
            resource=site_resource(site_id),
            now=now,
        )

    def require_view_site_execution(
        self, *, principal: Principal, site_id: str, now: datetime
    ) -> AuthorizationDecision:
        """Read a site's standing-order execution. Same site scope as IssueHalt."""
        return self._authorize(
            principal=principal,
            action=VIEW_SITE_EXECUTION,
            resource=site_resource(site_id),
            now=now,
        )

    # -- the parchi --------------------------------------------------------------

    def require_view_parchi(
        self, *, principal: Principal, parchi: Parchi, now: datetime
    ) -> AuthorizationDecision:
        """Read a parchi. The worker named on it, and the supervisor of its site, and nobody
        else -- in particular not a facilitator, who may assist with a claim without being
        handed the worker's record."""
        return self._authorize(
            principal=principal,
            action=VIEW_PARCHI,
            resource=parchi_resource(parchi),
            now=now,
        )

    def require_assist_claim(
        self,
        *,
        principal: Principal,
        consent: ClaimAssistanceContext,
        now: datetime,
    ) -> AuthorizationDecision:
        """Help a worker with a claim, against the CONSENT rather than the parchi.

        Note the resource: a `ClaimAssistanceContext`, not a `Parchi`. That is structural.
        A facilitator holding a parchi reference has no resource on which to name an assist
        request at all, so there is nothing for a permissive policy to accidentally match --
        while a facilitator holding a live consent matching their own id is allowed exactly
        this one action and still cannot read the record.
        """
        return self._authorize(
            principal=principal,
            action=ASSIST_CLAIM,
            resource=claim_assistance_resource(consent),
            now=now,
        )

    # -- the protected operation -------------------------------------------------

    def acknowledge_own_parchi(
        self,
        *,
        principal: Principal,
        payload: str,
        now: datetime,
        store: ParchiAckStore,
        tokens: AcknowledgementTokenStore,
        ledger: IdempotencyLedger,
        audit: AuditLog,
        event_id: str | None = None,
    ) -> AcknowledgementOutcome:
        """Confirm the parchi named by `payload`, as `principal`.

        The order is the whole design:

          1. **Resolve the link.** Which parchi is being confirmed? A malformed or unknown
             link is refused before anything is asked of the authorizer. Resolution reads;
             it does not consume, so a replay reaches the same decision a first attempt does.
          2. **Authorize.** Cedar decides whether this principal may perform
             `AcknowledgeOwnParchi` on that parchi, against `resource.worker == principal`.
          3. **Act.** The domain runs, and re-checks the identity rule itself.

        Steps 2 and 3 will refuse the same request. That is the intent, not a defect: see the
        module docstring, and `test_13` for the test that keeps it true.
        """
        parchi = resolve_parchi_for_payload(payload=payload, now=now, store=store, tokens=tokens)

        self._authorize(
            principal=principal,
            action=ACKNOWLEDGE_OWN_PARCHI,
            resource=parchi_resource(parchi),
            now=now,
        )

        return acknowledge_parchi(
            payload=payload,
            actor_worker_id=principal.principal_id,
            now=now,
            store=store,
            tokens=tokens,
            ledger=ledger,
            audit=audit,
            event_id=event_id,
        )

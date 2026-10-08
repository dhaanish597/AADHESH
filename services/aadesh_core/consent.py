"""Worker consent for facilitator assistance.

The rule this module exists to make expressible: **a facilitator may help with a claim only
while the worker's consent for it is granted and live.** Everything else about the model is
in service of that sentence being checkable.

Why a record rather than a boolean. The parchi used to carry `shared_for_assistance: bool`,
and a flag cannot say any of the things this decision actually turns on:

  * consent is granted to A PERSON, not switched on for a role
  * it starts at a moment and lapses at a moment
  * it can be withdrawn while it is still live

A boolean can only be true or false, so "granted, and withdrawn an hour later" and "never
granted" are the same value -- and they are not the same fact. `consent_granted` and
`revoked_at` are therefore kept INDEPENDENT here: a revoked consent still reports that the
worker did grant it. Collapsing them would erase the fact that the worker once chose to share,
which is itself worth being able to show.

**This module does not decide anything.** It holds state and enforces that the state is
well-formed. Whether a consent authorizes an action at a given instant is a Cedar decision,
made by comparing `expires_at`/`revoked_at`/`granted_at` against the request's `now` in
`infra/cedar/policies.cedar`. There is deliberately no `is_live(now)` helper here: a Python
predicate sitting next to the policy is an invitation for a caller to use it, and then the
rule would live in two places and the audited one would be the one not running.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class ClaimAssistanceContext:
    """One worker's consent for one facilitator to assist with one claim.

    Carries ids only. There is no worker name, contact detail or identity document here, and
    adding one would breach the minimisation rule the rest of the parchi design follows --
    the facilitator is being given a way to help with a claim, not a copy of the worker.

    `parchi_id` is a REFERENCE. The facilitator's authorization is computed against this
    context, never against the parchi, so holding a context never implies reading the record.
    """

    context_id: str
    parchi_id: str
    worker_id: str
    facilitator_id: str
    granted_at: datetime
    expires_at: datetime
    consent_granted: bool = False
    """Whether the WORKER has granted this. False is the state a request starts in.

    Kept as a field rather than implied by the object's existence so that the two negative
    cases stay distinguishable AND so the Cedar condition on it is not vacuous: a facilitator
    who has asked for help holds a context, and holding one must not be the same as being
    allowed to use it.
    """

    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("context_id", "parchi_id", "worker_id", "facilitator_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"ClaimAssistanceContext requires a non-empty {name}")

        for name in ("granted_at", "expires_at", "revoked_at"):
            moment = getattr(self, name)
            if moment is not None and moment.tzinfo is None:
                raise ValueError(
                    f"ClaimAssistanceContext.{name} must be timezone-aware. A naive datetime "
                    f"is not an instant, and reading it as one is how a consent window ends up "
                    f"hours away from what the worker agreed to."
                )

        if self.expires_at <= self.granted_at:
            raise ValueError(
                f"Consent {self.context_id} expires at or before it was granted. A consent "
                f"that is never live authorizes nothing; that is a configuration error, not a "
                f"decision to be discovered at runtime."
            )
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise ValueError(f"Consent {self.context_id} was revoked before it was granted.")


def _request(
    *,
    context_id: str,
    parchi_id: str,
    worker_id: str,
    facilitator_id: str,
    granted_at: datetime,
    ttl: timedelta,
    consent_granted: bool,
) -> ClaimAssistanceContext:
    if ttl <= timedelta(0):
        raise ValueError(
            f"Consent ttl must be positive; got {ttl!r}. A consent that expires the moment it "
            f"is granted would deny silently, which reads as a bug rather than a policy."
        )
    if not str(facilitator_id).strip() or facilitator_id == worker_id:
        raise ValueError(
            f"A consent cannot name the worker ({worker_id!r}) as their own facilitator. "
            f"Assistance is a second person's act, and this would make the facilitator check "
            f"satisfiable by the worker themselves."
        )

    return ClaimAssistanceContext(
        context_id=context_id,
        parchi_id=parchi_id,
        worker_id=worker_id,
        facilitator_id=facilitator_id,
        granted_at=granted_at,
        expires_at=granted_at + ttl,
        consent_granted=consent_granted,
    )


def request_assistance(
    *,
    context_id: str,
    parchi_id: str,
    worker_id: str,
    facilitator_id: str,
    requested_at: datetime,
    ttl: timedelta,
) -> ClaimAssistanceContext:
    """Open a consent NAMING a facilitator, before the worker has agreed to anything.

    This is the state a facilitator is in the moment they ask for help. It authorizes nothing
    -- `consentGranted` is False and the policy denies on it -- and that is the point: having
    a context is not having permission.
    """
    return _request(
        context_id=context_id,
        parchi_id=parchi_id,
        worker_id=worker_id,
        facilitator_id=facilitator_id,
        granted_at=requested_at,
        ttl=ttl,
        consent_granted=False,
    )


def grant_consent(
    *,
    context_id: str,
    parchi_id: str,
    worker_id: str,
    facilitator_id: str,
    granted_at: datetime,
    ttl: timedelta,
) -> ClaimAssistanceContext:
    """Record that a worker has authorized one facilitator to help with one claim.

    The caller supplies `granted_at` rather than the function reading a clock, for the same
    reason nothing else in the core does: a consent whose start time came from an ambient
    clock could not be reproduced, and the record of when a worker opted in is evidence.
    """
    return _request(
        context_id=context_id,
        parchi_id=parchi_id,
        worker_id=worker_id,
        facilitator_id=facilitator_id,
        granted_at=granted_at,
        ttl=ttl,
        consent_granted=True,
    )


def revoke_consent(consent: ClaimAssistanceContext, *, now: datetime) -> ClaimAssistanceContext:
    """Withdraw a consent. Idempotent, and the FIRST withdrawal is the one recorded.

    Re-revoking must not move the timestamp. The moment the worker withdrew is a fact about
    when they stopped agreeing to something, and a later call overwriting it would rewrite
    that fact -- the same reason sealing is not repeatable elsewhere in this codebase.
    """
    if consent.revoked_at is not None:
        return consent
    return replace(consent, revoked_at=now)

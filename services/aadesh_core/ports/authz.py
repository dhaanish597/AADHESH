"""Authorization port.

Authorization is a port rather than a function so the policy engine can be swapped without
touching callers -- and, more importantly, so callers physically cannot reach past it into an
`if principal.role == ...`. The decision type carries a human sentence because a denial in
Aadesh is something a user reads, not a status code they hit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from aadesh_core.domain import Principal


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A reference to another entity, used for attributes like `Parchi.worker`.

    Needed because `resource.worker == principal` is an entity comparison in Cedar, not a
    string comparison. Keeping it explicit stops an adapter guessing which strings are ids.
    """

    entity_type: str
    entity_id: str


@dataclass(frozen=True, slots=True)
class AuthzResource:
    """The resource half of an authorization request, in engine-neutral form."""

    entity_type: str
    entity_id: str
    attributes: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    """The outcome, with the reason stated in words a user can read.

    `policy_id` is the @id annotation of the policy that decided it, when there is one. An
    implicit denial -- nothing permitted the action -- has no policy_id, and still gets a
    sentence.
    """

    allowed: bool
    policy_id: str | None
    reason: str


@runtime_checkable
class AuthorizationProvider(Protocol):
    """Decides whether `principal` may perform `action` on `resource`.

    Implementations MUST fail closed: if a decision cannot be reached, raise
    AuthorizationUnavailable rather than returning allowed=True.
    """

    def authorize(
        self, *, principal: Principal, action: str, resource: AuthzResource
    ) -> AuthorizationDecision: ...

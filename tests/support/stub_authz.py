"""A configurable authorization provider for explanation tests.

Not `AllowAllTestOnly` -- explanation authorization tests need to DENY specific actions and
assert the model was never called. This records every request so a test can prove the denial
short-circuited before any context was gathered.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aadesh_core.domain import Principal
from aadesh_core.ports.authz import AuthorizationDecision, AuthzResource


class StubAuthzProvider:
    """Allows by default; denies any action named in `deny_actions` (or everything)."""

    def __init__(self, *, allowed: bool = True, deny_actions: frozenset[str] = frozenset()) -> None:
        self._allowed = allowed
        self._deny = set(deny_actions)
        self.requests: list[tuple[Principal, str, AuthzResource]] = []

    def authorize(
        self,
        *,
        principal: Principal,
        action: str,
        resource: AuthzResource,
        context: Mapping[str, Any] | None = None,
    ) -> AuthorizationDecision:
        self.requests.append((principal, action, resource))
        allowed = self._allowed and action not in self._deny
        return AuthorizationDecision(
            allowed=allowed,
            policy_id=None,
            reason=f"stub {'permits' if allowed else 'denies'} {action}",
        )


__all__ = ["StubAuthzProvider"]

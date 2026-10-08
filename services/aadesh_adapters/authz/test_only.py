"""An authorization provider that permits everything. TEST ENVIRONMENTS ONLY.

This exists so tests of non-authorization behaviour do not have to thread a policy engine
through every fixture. It is also, obviously, a component that would void every security
property Aadesh claims if it ever ran for real -- so it refuses to construct unless
AADESH_ENV is exactly "test".

The name is deliberately hard to read past in a diff.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from aadesh_core.domain import Principal
from aadesh_core.errors import TestOnlyComponentInProduction
from aadesh_core.ports.authz import AuthorizationDecision, AuthzResource

REQUIRED_ENV = "test"


class AllowAllTestOnly:
    """Allows every action. Constructing this outside AADESH_ENV=test raises."""

    def __init__(self) -> None:
        env = os.environ.get("AADESH_ENV")
        if env != REQUIRED_ENV:
            raise TestOnlyComponentInProduction(
                f"AllowAllTestOnly permits every action and must never run outside tests. "
                f"AADESH_ENV is {env!r}, expected {REQUIRED_ENV!r}. "
                f"Use CedarAuthorizationProvider instead."
            )

    def authorize(
        self,
        *,
        principal: Principal,
        action: str,
        resource: AuthzResource,
        context: Mapping[str, Any] | None = None,
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=True,
            policy_id=None,
            reason=(
                f"Permitted by AllowAllTestOnly, which is a test fixture and enforces "
                f"nothing. {principal.role} -> {action} on {resource.entity_type}."
            ),
        )

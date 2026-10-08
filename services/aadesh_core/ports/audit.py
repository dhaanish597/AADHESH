"""Audit port. A compliance tool with no audit trail is not a compliance tool.

Every authorization decision, obligation resolution and parchi transition is recorded. The
CloudWatch adapter satisfies this port in AWS; stdout satisfies it locally.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuditLog(Protocol):
    def record(self, *, event: str, detail: Mapping[str, Any]) -> None:
        """Append an audit event. MUST NOT raise -- losing an audit line must not fail a
        halt, though it should be visible in the sink's own error channel."""
        ...

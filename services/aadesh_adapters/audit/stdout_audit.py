"""Stdout audit log. The local stand-in for CloudWatch.

`record` swallows its own failures on purpose: losing an audit line must not abort a halt
that is legally in force. The failure is reported to stderr so it is still visible.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO


class StdoutAuditLog:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def record(self, *, event: str, detail: Mapping[str, Any]) -> None:
        try:
            line = json.dumps(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "event": event,
                    "detail": dict(detail),
                },
                default=str,
                sort_keys=True,
            )
            print(line, file=self._stream)
        except Exception as exc:
            print(f"AUDIT SINK FAILED for {event!r}: {exc}", file=sys.stderr)

"""The CloudWatch audit sink: every audit event is one structured JSON line on stdout.

Why stdout rather than `PutLogEvents`. A Lambda's stdout IS CloudWatch Logs -- the platform
ships it there, retains it for the configured retention window, and indexes it for Logs
Insights. Calling the CloudWatch Logs API from inside the function would add an IAM grant, a
client, and a failure mode, to reach the same place the platform already puts the data. So the
"CloudWatch audit log" is a structured log line, and the responsibilities below are what makes
it more than `print`.

Two responsibilities beyond a plain line:

  * **Denials emit an EMF metric.** Every authorization denial is written as a CloudWatch
    Embedded Metric Format record, so a dashboard or alarm can count denials without parsing
    log text. Denials are the signal an operator actually needs to see move.
  * **It never fails the caller.** The port says so: losing an audit line must not abort a
    halt that is legally in force. A serialisation failure is reported to stderr and swallowed.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

DENIAL_EVENT_MARKERS = ("Denied", "Denial", "Forbidden", "Refused")
NAMESPACE = "Aadesh/Authorization"


class CloudWatchAuditLog:
    """Satisfies the `AuditLog` port. One JSON line per event, plus an EMF metric on a denial."""

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
            if self._is_denial(event):
                self._emit_denial_metric(event, detail)
        except Exception as exc:
            print(f"AUDIT SINK FAILED for {event!r}: {exc}", file=sys.stderr)

    @staticmethod
    def _is_denial(event: str) -> bool:
        return any(marker in event for marker in DENIAL_EVENT_MARKERS)

    def _emit_denial_metric(self, event: str, detail: Mapping[str, Any]) -> None:
        """A CloudWatch EMF record: a metric a dashboard can read without parsing text."""
        record = {
            "_aws": {
                "Timestamp": int(datetime.now(UTC).timestamp() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": NAMESPACE,
                        "Dimensions": [["Event"]],
                        "Metrics": [{"Name": "Denials", "Unit": "Count"}],
                    }
                ],
            },
            "Event": event,
            "Denials": 1,
            "policy_id": str(detail.get("policy_id", "") or ""),
        }
        print(json.dumps(record, sort_keys=True), file=self._stream)

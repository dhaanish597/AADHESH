"""In-memory TaskTokenStore. The reference the DynamoDB adapter is held to."""

from __future__ import annotations

import threading
from datetime import datetime


class InMemoryTaskTokenStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}

    def put(self, *, parchi_id: str, task_token: str, expires_at: datetime) -> None:
        if expires_at.tzinfo is None:
            raise ValueError(
                "TaskTokenStore.put requires a timezone-aware expires_at. A naive datetime "
                "would be compared against the Lambda clock in an unknown zone."
            )
        with self._lock:
            self._tokens[parchi_id] = task_token

    def pop(self, *, parchi_id: str) -> str | None:
        with self._lock:
            return self._tokens.pop(parchi_id, None)

    def peek(self, *, parchi_id: str) -> str | None:
        with self._lock:
            return self._tokens.get(parchi_id)

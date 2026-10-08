"""AQI provider port.

Aadesh reads station-level air quality to record WHAT THE AIR WAS when a halt was issued. It
does not use the number to decide the GRAP stage -- a stage is invoked by a CAQM order. The
reading is evidence attached to a record, plus the input to an *implied* stage shown
alongside the invoked one.

Every implementation must stamp provenance. CPCB station data is hourly, so `observed_at` and
`ingested_at` are both required and the gap between them is the honest answer to "how fresh
is this?".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aadesh_core.domain import StationReading


@runtime_checkable
class AqiProvider(Protocol):
    def station_ids(self) -> tuple[str, ...]:
        """Stations this provider can serve."""
        ...

    def latest_reading(self, *, station_id: str) -> StationReading | None:
        """Most recent reading for `station_id`, or None if there is none.

        MUST return None for an unknown station rather than raising: a missing reading is an
        ordinary condition, and the caller's job is to show "no reading" honestly.
        """
        ...

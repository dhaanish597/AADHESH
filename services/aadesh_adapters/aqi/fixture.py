"""Fixture AQI provider: synthetic placeholder readings, loudly labelled.

This exists so the system can be exercised end to end before a real AQI source is wired up.
The values in the fixture file are invented and mean nothing -- which is precisely why every
reading it returns is stamped `provenance=SYNTHETIC`, and why there is no way to override
that from the file or the constructor.

The alternative -- inventing plausible Delhi AQI numbers and letting them flow through
unlabelled -- would make the system demo well and be dishonest, which is the trade this
project exists to refuse.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aadesh_core.domain import Provenance, StationReading


class FixtureAqiProvider:
    """Serves readings from a JSON fixture. Always SYNTHETIC."""

    def __init__(self, *, path: Path) -> None:
        self._path = Path(path)
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        self._stations: dict[str, dict] = {s["station_id"]: s for s in payload.get("stations", [])}

    def station_ids(self) -> tuple[str, ...]:
        return tuple(self._stations)

    def latest_reading(self, *, station_id: str) -> StationReading | None:
        entry = self._stations.get(station_id)
        if entry is None:
            return None
        return StationReading(
            station_id=entry["station_id"],
            parameter=entry["parameter"],
            value=float(entry["value"]),
            observed_at=datetime.fromisoformat(entry["observed_at"]),
            ingested_at=datetime.fromisoformat(entry["ingested_at"]),
            # Not read from the fixture. A placeholder cannot promote itself.
            provenance=Provenance.SYNTHETIC,
        )

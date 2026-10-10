"""DynamoDB store for station readings.

A reading is evidence, not decision input: the stage comes from a CAQM order, never from
arithmetic on a number in this table. What the table is for is the honest answer to "how
fresh is the reading, and where did it come from?" -- so every item carries a `provenance`
label and the two timestamps (`observed_at` when the station measured, `ingested_at` when
Aadesh saw it). Nothing here can be relabelled: `StationReading` has no independent provenance
setter, and the loader reconstructs the label from the stored record rather than accepting one
from the caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aadesh_adapters.store.dynamo.client import (
    dynamo_resource,
    table_name,
)
from aadesh_adapters.store.dynamo.serde import dumps, loads
from aadesh_core.domain import Provenance, StationReading


class DynamoReadingsStore:
    def __init__(self, *, dynamo: Any = None, table_name_override: str | None = None) -> None:
        self._table_name = table_name_override or table_name("readings")
        self._dynamo = dynamo
        self._table = None

    @property
    def table(self) -> Any:
        if self._table is None:
            self._table = (self._dynamo or dynamo_resource()).Table(self._table_name)
        return self._table

    def put(self, reading: StationReading) -> None:
        import json

        self.table.put_item(
            Item={
                "station_id": reading.station_id,
                "observed_at": reading.observed_at.isoformat(),
                "parameter": reading.parameter,
                "provenance": reading.provenance.value,
                "record": json.dumps(dumps(reading), sort_keys=True, ensure_ascii=False),
            }
        )

    def latest(self, station_id: str) -> StationReading | None:
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key("station_id").eq(station_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if not items or not items[0].get("record"):
            return None
        import json

        return loads(json.loads(items[0]["record"]), StationReading)


def replay_placeholder(
    *,
    station_id: str,
    parameter: str,
    value: float,
    observed_at: datetime,
    ingested_at: datetime,
) -> StationReading:
    """A recorded observation, labelled REPLAY.

    Used to seed a deployment with the observation the corpus's January replay refers to. The
    label is the point: a value that is real but not current must never be presented as if it
    were measured now, and `Provenance.REPLAY` is how that is made structural.
    """
    return StationReading(
        station_id=station_id,
        parameter=parameter,
        value=value,
        observed_at=observed_at,
        ingested_at=ingested_at,
        provenance=Provenance.REPLAY,
    )

"""AQI ingestion handler — EventBridge triggered, reads station data.

Reads from OpenAQ (or CPCB nearest station), writes to DynamoDB with
provenance stamp. Does NOT decide any GRAP stage — stages come from
CAQM orders, not from arithmetic on readings.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import requests

REGION = os.environ.get("AWS_REGION", "ap-south-1")
TABLE_READINGS = os.environ.get("AADESH_TABLE_READINGS", "aadesh-readings")
STATION_ID = os.environ.get("AADESH_STATION_ID", "DL-NCR-ROHINI-01")
STALENESS_SECONDS = int(os.environ.get("AADESH_READING_STALENESS_SECONDS", "5400"))
OPENAQ_BASE_URL = os.environ.get("OPENAQ_BASE_URL", "https://api.openaq.org/v3")
OPENAQ_API_KEY = os.environ.get("OPENAQ_API_KEY", "")

_logger = boto3.client("logs")


def handle(event: dict, context: Any) -> dict:
    """EventBridge scheduled invocation — ingest latest reading."""
    try:
        reading = _fetch_reading()
        if reading:
            _store_reading(reading)
            return {"status": "ok", "station_id": reading.station_id, "value": reading.value}
        return {"status": "no_data", "station_id": STATION_ID}
    except Exception as e:
        _log_error(str(e))
        return {"status": "error", "reason": str(e)}


def _fetch_reading():
    """Fetch latest reading from OpenAQ for configured station."""
    # For demo/development, return synthetic reading
    if not OPENAQ_API_KEY:
        return _synthetic_reading()

    try:
        resp = requests.get(
            f"{OPENAQ_BASE_URL}/measurements",
            params={
                "station_id": STATION_ID,
                "parameter": "pm25",
                "limit": 1,
                "sort": "desc",
            },
            headers={"X-API-Key": OPENAQ_API_KEY} if OPENAQ_API_KEY else {},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        result = results[0]
        return _reading_from_openaq(result)

    except Exception:
        return _synthetic_reading()


def _reading_from_openaq(result: dict):
    """Convert OpenAQ result to StationReading."""
    from aadesh_core.domain import Provenance, StationReading

    return StationReading(
        station_id=STATION_ID,
        parameter="PM2.5",
        value=float(result.get("value", 0)),
        observed_at=datetime.fromisoformat(result.get("datetime", {}).get("utc", "")),
        ingested_at=datetime.now(UTC),
        provenance=Provenance.MEASURED,
    )


def _synthetic_reading():
    """Return a synthetic reading for demo/testing."""
    from aadesh_core.domain import Provenance, StationReading

    return StationReading(
        station_id=STATION_ID,
        parameter="PM2.5",
        value=285.0,  # Stage III threshold exceeded
        observed_at=datetime.now(UTC) - timedelta(hours=1),
        ingested_at=datetime.now(UTC),
        provenance=Provenance.SYNTHETIC,
    )


def _store_reading(reading):
    """Store reading in DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_READINGS)

    table.put_item(Item={
        "station_id": reading.station_id,
        "observed_at": reading.observed_at.isoformat(),
        "parameter": reading.parameter,
        "value": reading.value,
        "ingested_at": reading.ingested_at.isoformat(),
        "provenance": reading.provenance.value,
        "staleness_seconds": STALENESS_SECONDS,
        "freshness": "FRESH" if _is_fresh(reading) else "STALE",
        "inserted_at": datetime.now(UTC).isoformat(),
    })


def _is_fresh(reading) -> bool:
    age = datetime.now(UTC) - reading.observed_at
    return age.total_seconds() <= STALENESS_SECONDS


def _log_error(message: str):
    """Log error to CloudWatch."""
    import boto3
    log = boto3.client("logs", region_name=REGION)
    log.put_log_events(
        logGroupName=f"/aws/lambda/aadesh-ingest",
        logStreamName="ingest",
        logEvents=[{
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "message": f"ERROR: {message}",
        }],
    )

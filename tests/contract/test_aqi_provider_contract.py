"""Contract suite for the AqiProvider port, plus the fixture adapter's own rules.

The contract tests are parametrised over adapters so that when the OpenAQ and replay
adapters land they are held to exactly the same behaviour as the fake. That is the point of
having a port at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aadesh_adapters.aqi.fixture import FixtureAqiProvider
from aadesh_core.domain import Provenance
from aadesh_core.ports.aqi import AqiProvider

NOW = datetime(2026, 10, 8, 9, 30, tzinfo=UTC)


@pytest.fixture
def fixture_provider(repo_root):
    return FixtureAqiProvider(
        path=repo_root / "fixtures" / "readings" / "placeholder_readings.json"
    )


ADAPTERS = ["fixture_provider"]


# --- shared port contract --------------------------------------------------


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_adapter_satisfies_the_port(adapter_name, request):
    assert isinstance(request.getfixturevalue(adapter_name), AqiProvider)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_unknown_station_returns_none_rather_than_raising(adapter_name, request):
    provider = request.getfixturevalue(adapter_name)
    assert provider.latest_reading(station_id="no-such-station") is None


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_a_returned_reading_always_declares_its_provenance(adapter_name, request):
    provider = request.getfixturevalue(adapter_name)
    station = provider.station_ids()[0]
    reading = provider.latest_reading(station_id=station)
    assert reading is not None
    assert isinstance(reading.provenance, Provenance)


@pytest.mark.parametrize("adapter_name", ADAPTERS)
def test_observed_at_is_timezone_aware(adapter_name, request):
    """A naive timestamp is a staleness bug waiting to happen."""
    provider = request.getfixturevalue(adapter_name)
    reading = provider.latest_reading(station_id=provider.station_ids()[0])
    assert reading.observed_at.tzinfo is not None


# --- the fixture adapter's specific obligation -----------------------------


def test_fixture_readings_are_labelled_synthetic(fixture_provider):
    """The whole reason this adapter is safe to ship: it cannot be mistaken for a measurement."""
    for station in fixture_provider.station_ids():
        reading = fixture_provider.latest_reading(station_id=station)
        assert reading.provenance is Provenance.SYNTHETIC


def test_fixture_file_declares_itself_a_placeholder(repo_root):
    import json

    payload = json.loads(
        (repo_root / "fixtures" / "readings" / "placeholder_readings.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["provenance"] == "synthetic"
    assert "not a measurement" in payload["_warning"].lower()


def test_staleness_is_computed_against_an_injected_now(fixture_provider):
    reading = fixture_provider.latest_reading(station_id=fixture_provider.station_ids()[0])
    assert reading.is_stale(reading.observed_at + timedelta(hours=3), timedelta(hours=2))
    assert not reading.is_stale(reading.observed_at + timedelta(minutes=30), timedelta(hours=2))

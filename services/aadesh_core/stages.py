"""Deriving the IMPLIED GRAP stage from a station reading, using cited bands only.

This module exists to make a point precisely: Aadesh never computes the authoritative stage.
A stage is *invoked by a CAQM order*. What a reading can do is *imply* a stage, and only via
threshold bands that were themselves read out of a hashed order and cited.

So there is no arithmetic on AQI anywhere in this file beyond comparing a reading to bounds
that arrived as data. Until `corpus/stage_bands/` is populated, every call here returns
"undeterminable" -- which is the honest answer, and the one that distinguishes Aadesh from
the several dozen GRAP trackers that will hardcode `if aqi > 400`.
"""

from __future__ import annotations

from collections.abc import Sequence

from aadesh_core.domain import (
    ImpliedStage,
    InvokedStage,
    SourceState,
    StageBand,
    StageStatus,
    StationReading,
)
from aadesh_core.errors import CorpusIntegrityError


def _contains(band: StageBand, value: float) -> bool:
    if value < band.aqi_lower:
        return False
    if band.aqi_upper is None:
        return True
    return value <= band.aqi_upper


def derive_implied_stage(
    *,
    reading: StationReading | None,
    bands: Sequence[StageBand],
) -> ImpliedStage:
    """Imply a stage from `reading` using only VERIFIED bands.

    Returns an undeterminable ImpliedStage when there is no reading, no verified band, or no
    band covering the value. None of those is an error -- they are all "we cannot say", which
    Aadesh is required to be able to express.
    """
    if reading is None:
        return ImpliedStage(stage=None, citation=None, reading=None)

    verified = [b for b in bands if b.source_state is SourceState.VERIFIED]
    if not verified:
        return ImpliedStage(stage=None, citation=None, reading=reading)

    matches = [b for b in verified if _contains(b, reading.value)]
    if not matches:
        return ImpliedStage(stage=None, citation=None, reading=reading)

    if len({b.stage for b in matches}) > 1:
        raise CorpusIntegrityError(
            f"Reading {reading.value} from {reading.station_id} falls in overlapping stage "
            f"bands implying stages {sorted({b.stage for b in matches})}. The corpus cannot "
            f"be interpreted safely; fix the bands rather than guessing."
        )

    chosen = matches[0]
    return ImpliedStage(stage=chosen.stage, citation=chosen.citation, reading=reading)


def stage_status(
    *,
    invoked: InvokedStage | None,
    reading: StationReading | None,
    bands: Sequence[StageBand],
) -> StageStatus:
    """Build the single status line: what was invoked, and what the air implies."""
    return StageStatus(
        invoked=invoked,
        implied=derive_implied_stage(reading=reading, bands=bands),
    )

"""aadesh-resolve: local, verified, deterministic construction obligation resolution."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any

from aadesh_adapters.corpus.local_file import LocalFileCorpus
from aadesh_core.domain import ConstructionSite, Provenance, ReplayContext, StationReading
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.resolver import resolution_to_dict, resolve_obligations


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aadesh-resolve",
        description="Resolve recorded construction-site facts against a verified CAQM corpus.",
    )
    parser.add_argument("--site", required=True, type=Path)
    parser.add_argument("--corpus", default=Path("corpus"), type=Path)
    parser.add_argument("--now", help="ISO-8601 evaluation time with timezone; defaults to UTC now")
    parser.add_argument(
        "--replay", type=Path, help="JSON context selecting a verified historical invocation"
    )
    parser.add_argument(
        "--observation", type=Path, help="Existing observation JSON; derives implied stage only"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        site = ConstructionSite.from_dict(_read(args.site))
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
        replay = None
        if args.replay:
            payload = _read(args.replay)
            if payload.get("at") is not None:
                payload["at"] = datetime.fromisoformat(payload["at"])
            replay = ReplayContext(**payload)
        reading = None
        if args.observation:
            payload = _read(args.observation)
            payload["observed_at"] = datetime.fromisoformat(payload["observed_at"])
            payload["ingested_at"] = datetime.fromisoformat(payload["ingested_at"])
            payload["provenance"] = Provenance(payload["provenance"])
            reading = StationReading(**payload)
            if type(reading.value) not in (int, float) or not isfinite(reading.value):
                raise ValueError("Observation value must be a finite number")
            if reading.observed_at.utcoffset() is None or reading.ingested_at.utcoffset() is None:
                raise ValueError("Observation timestamps must include timezones")
            if not isinstance(reading.parameter, str) or not reading.parameter.strip():
                raise ValueError("Observation parameter must be a non-empty string")
        result = resolve_obligations(
            site=site,
            corpus=LocalFileCorpus(args.corpus).snapshot(),
            now=now,
            replay=replay,
            reading=reading,
        )
    except CorpusIntegrityError as exc:
        print(json.dumps({"error": "CORPUS_INTEGRITY", "reason": str(exc)}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": "INVALID_INPUT", "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(resolution_to_dict(result), indent=2, ensure_ascii=True, allow_nan=False))
    return 0 if result.fully_sourced else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

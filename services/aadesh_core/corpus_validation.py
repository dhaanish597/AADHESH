"""Schema and evidence-reference validation shared by ingestion, verification and loading."""

from __future__ import annotations

import json
import re
from math import isfinite
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from aadesh_core.citations import literal_is_cited, normalise, quote_names_stage
from aadesh_core.errors import CorpusIntegrityError

SCHEMA_DIR = Path(__file__).parent / "corpus_schemas"


def validate_entry(
    entry: dict[str, Any], schema_name: str, *, schema_dir: Path = SCHEMA_DIR
) -> None:
    schema_path = Path(schema_dir) / schema_name
    if not schema_path.exists():
        raise CorpusIntegrityError(f"Schema {schema_name} is missing from {schema_dir}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(entry)
    except JsonSchemaValidationError as exc:
        field = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise CorpusIntegrityError(
            f"{schema_name}: invalid entry at {field}: {exc.message}"
        ) from exc
    if schema_name == "obligation.schema.json":
        validate_rule_evidence(entry)
    elif schema_name == "stage_band.schema.json":
        validate_stage_band_evidence(entry)


def validate_stage_band_evidence(entry: dict[str, Any]) -> None:
    """Bind band values to the closed-range/strict-bound wording used by the corpus.

    This is a check on already encoded data, not extraction of legal rules from prose.
    An unsupported source format requires an explicit model change rather than a guess.
    """
    quote = normalise(entry["quote"])
    lower, upper = entry["aqi_lower"], entry.get("aqi_upper")
    inclusive = entry.get("aqi_lower_inclusive", True)
    if not isfinite(lower) or (upper is not None and (not isfinite(upper) or upper < lower)):
        raise CorpusIntegrityError("Stage band bounds must be finite and ordered")
    pollutant = re.escape(normalise(entry["pollutant"]))
    lower_text = re.escape(format(lower, "g"))
    if upper is None:
        comparison = ">=" if inclusive else ">"
        pattern = rf"\b{pollutant}\s*{comparison}\s*{lower_text}(?![\d.])"
        supported = re.search(pattern, quote) is not None
    else:
        upper_text = re.escape(format(upper, "g"))
        pattern = (
            rf"\b{pollutant}\s+(?:(?:is|ranging)\s+)?(?:between\s+)?"
            rf"{lower_text}\s*-\s*{upper_text}(?![\d.])"
        )
        supported = inclusive and re.search(pattern, quote) is not None
    if not supported or not quote_names_stage(quote, entry["stage"]):
        raise CorpusIntegrityError(
            f"Stage band {entry['stage']}: quote does not support the encoded stage, "
            "pollutant, bounds and inclusivity"
        )


def validate_rule_evidence(entry: dict[str, Any]) -> None:
    """Require cited literals and evidence for every decision, including compound logic.

    This proves the literals occur in the cited text, not the correctness of a legal
    interpretation. The latter still requires the documented, reviewable corpus audit.
    """
    evidence = {"clause": entry, **entry["evidence"]}

    def quotes_for(refs: list[str]) -> str:
        if not refs or any(ref not in evidence for ref in refs):
            raise CorpusIntegrityError(
                f"{entry['obligation_id']}: missing evidence reference {refs}"
            )
        return " ".join(normalise(evidence[ref]["quote"]) for ref in refs)

    stage_quote = quotes_for([entry["stage_evidence"]])
    if not quote_names_stage(stage_quote, entry["triggers_at_stage"]):
        raise CorpusIntegrityError(f"{entry['obligation_id']}: stage evidence does not name stage")
    quotes_for([entry["continuation_evidence"]])
    quotes_for(entry["action_evidence"])

    def check(predicate: dict) -> None:
        quotes = quotes_for(predicate["evidence"])
        if "conditions" in predicate:
            for child in predicate["conditions"]:
                check(child)
            return
        value = predicate["value"]
        values = value if isinstance(value, list) else [value]
        for literal in values:
            if not literal_is_cited(literal, quotes):
                raise CorpusIntegrityError(
                    f"{entry['obligation_id']}: uncited legal literal {literal!r} "
                    f"in predicate for {predicate['field']}"
                )

    check(entry["applicability"])
    check(entry["requirement"])
    if "clarification_when" in entry:
        check(entry["clarification_when"])

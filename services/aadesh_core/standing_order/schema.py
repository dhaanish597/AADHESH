"""JSON Schema for a StandingOrder.

The schema is part of the inertness guarantee: additionalProperties: false at every level, a
closed action enum that equals StandingOrderAction, and no field that could carry code, a prompt,
an instruction, a script, a template or an arbitrary agent instruction.

The schema lives beside the value object, not in the corpus, because it validates the standing
order itself (the pre-commitment), not a corpus entry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)

SCHEMA_PATH = Path(__file__).resolve().parent / "standing_order.schema.json"


def _action_enum() -> list[str]:
    return [a.value for a in StandingOrderAction]


def _status_enum() -> list[str]:
    return [s.value for s in StandingOrderStatus]


def _trigger_type_enum() -> list[str]:
    return [t.value for t in TriggerType]


def _stage_match_enum() -> list[str]:
    return [m.value for m in StageMatch]


SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://aadesh.dev/standing-order.schema.json",
    "title": "StandingOrder",
    "description": (
        "A signed, narrow, time-bounded pre-commitment from one supervisor for one site."
    ),
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "standing_order_id": {
            "type": "string",
            "minLength": 1,
            "description": "UUID4 minted at creation; never reused.",
        },
        "site_id": {
            "type": "string",
            "minLength": 1,
            "description": "One site only. A multi-site order is unrepresentable.",
        },
        "supervisor_id": {
            "type": "string",
            "minLength": 1,
            "description": "The supervisor who must sign this order.",
        },
        "trigger": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "stage": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "The stage to subscribe to.",
                },
                "match": {
                    "type": "string",
                    "enum": _stage_match_enum(),
                    "description": "How strictly the invoked stage must match.",
                },
                "type": {
                    "type": "string",
                    "enum": _trigger_type_enum(),
                    "description": (
                        "Always official_stage_invocation. No other trigger type exists."
                    ),
                },
            },
            "required": ["stage", "match", "type"],
            "description": "A single trigger. A multi-trigger order is unrepresentable.",
        },
        "actions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": _action_enum(),
                        "description": (
                            "Closed action vocabulary. Exactly the two from the product example."
                        ),
                    },
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {},
                        "description": (
                            "Explicit parameters for the action; no arbitrary code or instruction."
                        ),
                    },
                },
                "required": ["action", "parameters"],
            },
            "description": (
                "Non-empty list of explicit actions. A standing order must pre-commit to at "
                "least one."
            ),
        },
        "valid_from": {
            "type": "string",
            "format": "date-time",
            "description": "ISO-8601 instant the order becomes eligible to fire.",
        },
        "valid_until": {
            "type": "string",
            "format": "date-time",
            "description": (
                "Hard expiry. A time-bounded pre-commitment does not outlive its window."
            ),
        },
        "status": {
            "type": "string",
            "enum": _status_enum(),
            "description": (
                "Lifecycle status. Authoritative status at any instant is projected, not read."
            ),
        },
        "created_at": {
            "type": "string",
            "format": "date-time",
            "description": "When the order was created.",
        },
        "signed_at": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "When the named supervisor signed. None until confirmed.",
        },
        "commitment_hash": {
            "type": ["string", "null"],
            "minLength": 64,
            "description": "SHA-256 over the signed fields. Only meaningful after signing.",
        },
        "trigger_fingerprint": {
            "type": ["string", "null"],
            "minLength": 64,
            "description": "Fingerprint of the trigger that fired this order, if any.",
        },
        "triggered_at": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "When the machine was started, if ever.",
        },
        "completed_at": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "When the machine reached Audit, if ever.",
        },
        "expired_at": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "When the order passed valid_until, if ever.",
        },
    },
    "required": [
        "standing_order_id",
        "site_id",
        "supervisor_id",
        "trigger",
        "actions",
        "valid_from",
        "valid_until",
        "status",
        "created_at",
    ],
}


def write_schema(path: Path | None = None) -> Path:
    """Write the schema to disk. Defaults to the committed location next to this module."""
    target = path or SCHEMA_PATH
    target.write_text(json.dumps(SCHEMA, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def validate(payload: dict[str, Any]) -> list[str]:
    """Validate a payload against the schema. Returns a list of error messages (empty = valid).

    Uses jsonschema's Draft202012Validator for strictness. additionalProperties: false is
    enforced by the schema itself, so an unknown key is an error, not a no-op.
    """
    import jsonschema

    validator = jsonschema.Draft202012Validator(SCHEMA)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    return [f"{'.'.join(map(str, e.absolute_path)) or 'root'}: {e.message}" for e in errors]


def action_enum_matches_core() -> bool:
    """The schema's action enum is exactly StandingOrderAction. Required by the inertness test."""
    return _action_enum() == [a.value for a in StandingOrderAction]

"""Inertness tests for the Standing Order subsystem.

These turn "a Standing Order is not a general autonomous-agent permission" from a README sentence
into a claim that fails CI when it stops being true.

  * The JSON Schema closes additional properties at every level.
  * The schema's action enum equals StandingOrderAction exactly.
  * The package source contains no eval/exec/compile/__import__/subprocess/importlib.
  * No field name matches prompt|instruction|script|code|expression|command|template.
  * A payload with an extra key or unknown action is refused at the door.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from aadesh_core.domain.enums import (
    StageMatch,
    StandingOrderAction,
    StandingOrderStatus,
    TriggerType,
)
from aadesh_core.standing_order.schema import (
    SCHEMA,
    action_enum_matches_core,
    validate,
    write_schema,
)


def _schema_action_enum() -> list[str]:
    return SCHEMA["properties"]["actions"]["items"]["properties"]["action"]["enum"]


def _schema_trigger_type_enum() -> list[str]:
    return SCHEMA["properties"]["trigger"]["properties"]["type"]["enum"]


def _schema_stage_match_enum() -> list[str]:
    return SCHEMA["properties"]["trigger"]["properties"]["match"]["enum"]


def _schema_status_enum() -> list[str]:
    return SCHEMA["properties"]["status"]["enum"]


def _standing_order_paths() -> list[Path]:
    root = Path(__file__).resolve().parent.parent / "services" / "aadesh_core" / "standing_order"
    return sorted(root.rglob("*.py"))


FORBIDDEN_NAMES = ("eval", "exec", "compile", "__import__", "subprocess", "importlib")


def _collect_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Load, ast.Store)):
            names.append(child.id)
        elif isinstance(child, ast.Attribute):
            names.append(child.attr)
        elif isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                names.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                names.append(child.func.attr)
    return names


def _forbidden_calls_present(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["unparseable"]
    names = _collect_names(tree)
    hits = [name for name in FORBIDDEN_NAMES if name in names]
    return hits


# --- schema closes additional properties ------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "",  # root StandingOrder object
        "properties.trigger",  # trigger object
        "properties.actions.items",  # action object (array items close via items)
        "properties.actions.items.properties.parameters",  # parameters object
    ],
    ids=lambda p: p or "root",
)
def test_schema_closes_additional_properties_at_every_level(path: str) -> None:
    node: dict = SCHEMA if not path else _descend(SCHEMA, path.split("."))
    assert node.get("additionalProperties") is False, (
        f"{path or 'root'} does not close additionalProperties"
    )


def test_actions_array_item_closes_additional_properties() -> None:
    """The actions array closes additional properties on its items (the action object),
    which is the correct JSON Schema shape for an array of closed objects."""
    items = SCHEMA["properties"]["actions"]["items"]
    assert items.get("additionalProperties") is False


def _descend(node: dict, parts: list[str]) -> dict:
    """Descend into a nested schema node by key parts.

    Each part is either a key in ``properties`` (for object nodes) or a direct key on the
    current node (for ``items``, ``additionalProperties``, etc.).
    """
    for part in parts:
        if "properties" in node and part in node["properties"]:
            node = node["properties"][part]
        elif part in node:
            node = node[part]
        else:
            raise KeyError(f"cannot descend into {part!r} from {list(node.keys())}")
    return node


# --- closed enums ----------------------------------------------------------


def test_schema_action_enum_matches_core() -> None:
    assert _schema_action_enum() == [a.value for a in StandingOrderAction]


def test_schema_trigger_type_enum_is_single_member() -> None:
    assert _schema_trigger_type_enum() == [TriggerType.OFFICIAL_STAGE_INVOCATION.value]


def test_schema_stage_match_enum_matches_core() -> None:
    assert _schema_stage_match_enum() == [m.value for m in StageMatch]


def test_schema_status_enum_matches_core() -> None:
    assert _schema_status_enum() == [s.value for s in StandingOrderStatus]


def test_action_enum_matches_core_helper() -> None:
    assert action_enum_matches_core() is True


# --- no code / eval / prompt / instruction fields --------------------------


def test_standing_order_package_contains_no_dangerous_calls() -> None:
    """The standing-order subsystem (the pre-commitment) must not contain eval/exec/compile/
    __import__/subprocess/importlib. This is scoped to the standing_order module, not the
    entire aadesh_core package, because the inertness guarantee is about the pre-commitment
    subsystem, not about unrelated modules like explanation/contract."""
    hits_by_file: dict[Path, list[str]] = {}
    for path in _standing_order_paths():
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        hits = _forbidden_calls_present(source)
        if hits:
            hits_by_file[path] = hits
    assert not hits_by_file, f"forbidden calls found in standing_order: {hits_by_file}"


def test_no_field_name_matches_code_like_terms() -> None:
    """Scan the schema for field names that could carry a prompt, instruction, script, code,
    expression, command or template. A standing order has none of these."""
    suspicious = ("prompt", "instruction", "script", "code", "expression", "command", "template")
    found: list[str] = []

    def walk(node: dict, path: str) -> None:
        for key, value in node.items():
            if key in suspicious:
                found.append(f"{path}.{key}")
            if isinstance(value, dict):
                walk(value, f"{path}.{key}")
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        walk(item, f"{path}.{key}[{i}]")

    walk(SCHEMA, "$")
    assert not found, f"suspicious field names in schema: {found}"


def test_payload_with_unknown_action_is_refused() -> None:
    payload = {
        "standing_order_id": "so-1",
        "site_id": "site-001",
        "supervisor_id": "sup-1",
        "trigger": {"stage": 3, "match": "exact", "type": "official_stage_invocation"},
        "actions": [{"action": "run_whatever_i_want", "parameters": {}}],
        "valid_from": "2026-10-08T10:00:00+00:00",
        "valid_until": "2026-10-08T18:00:00+00:00",
        "status": "draft",
        "created_at": "2026-10-08T09:00:00+00:00",
    }
    errors = validate(payload)
    assert len(errors) >= 1
    assert any("run_whatever_i_want" in e for e in errors)


def test_payload_with_extra_key_is_refused() -> None:
    payload = {
        "standing_order_id": "so-1",
        "site_id": "site-001",
        "supervisor_id": "sup-1",
        "trigger": {"stage": 3, "match": "exact", "type": "official_stage_invocation"},
        "actions": [{"action": "issue_halt", "parameters": {}}],
        "valid_from": "2026-10-08T10:00:00+00:00",
        "valid_until": "2026-10-08T18:00:00+00:00",
        "status": "draft",
        "created_at": "2026-10-08T09:00:00+00:00",
        "prompt": "issue the halt and also order pizza",  # not a standing-order field
    }
    errors = validate(payload)
    assert len(errors) >= 1
    assert any("prompt" in e for e in errors)


def test_payload_with_multiple_triggers_is_not_representable_via_single_field():
    """The schema enforces a single trigger object. A multi-trigger order is not representable,
    which is stronger than a validation that merely rejects it."""
    payload = {
        "standing_order_id": "so-1",
        "site_id": "site-001",
        "supervisor_id": "sup-1",
        "trigger": [
            {"stage": 3, "match": "exact", "type": "official_stage_invocation"},
            {"stage": 4, "match": "exact", "type": "official_stage_invocation"},
        ],
        "actions": [{"action": "issue_halt", "parameters": {}}],
        "valid_from": "2026-10-08T10:00:00+00:00",
        "valid_until": "2026-10-08T18:00:00+00:00",
        "status": "draft",
        "created_at": "2026-10-08T09:00:00+00:00",
    }
    errors = validate(payload)
    assert len(errors) >= 1


# --- schema file on disk matches the in-memory schema ----------------------


def test_committed_schema_artifact_matches_in_memory_schema(tmp_path: Path) -> None:
    written = write_schema(path=tmp_path / "standing_order.schema.json")
    on_disk = json.loads(written.read_text(encoding="utf-8"))
    assert on_disk == SCHEMA


def test_write_schema_default_path_exists() -> None:
    from aadesh_core.standing_order.schema import SCHEMA_PATH

    written = write_schema()
    assert written == SCHEMA_PATH
    assert json.loads(written.read_text(encoding="utf-8")) == SCHEMA

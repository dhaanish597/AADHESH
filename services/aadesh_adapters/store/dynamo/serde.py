"""Round-trip serialisation for the records DynamoDB holds.

Written by hand rather than with `dataclasses.asdict` for three reasons, each of which is a
way a stored record stops being the record that was signed:

  * `asdict` renders a StrEnum as a bare string with nothing to validate it against;
  * it cannot distinguish an absent key from a null one;
  * it silently ignores a field added to the dataclass later, so a newer writer and an older
    reader disagree without either noticing.

`loads` reconstructs from the type hints and refuses a payload whose key set does not match
the dataclass exactly. Adding a field to `Parchi` therefore breaks loudly here, which is the
behaviour we want from the one place evidence records cross a durability boundary.
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


class SerdeError(ValueError):
    """A record could not be serialised or reconstructed without loss."""


def _encode(value: Any) -> Any:
    # Enum is checked BEFORE str/int, deliberately. A StrEnum member IS a str, so the scalar
    # branch below would return the member itself rather than its value.
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SerdeError(
                "Refusing to serialise a naive datetime. Every timestamp on a stored record "
                "is compared against a timezone-aware clock."
            )
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    if isinstance(value, Mapping):
        # frozendict is a dict subclass, so this covers StandingOrderActionClause.parameters.
        return {str(k): _encode(v) for k, v in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    raise SerdeError(f"No codec for {type(value).__name__}.")


def _decode(value: Any, hint: Any) -> Any:
    if hint is Any or hint is None:
        return value

    origin = get_origin(hint)

    # BOTH spellings of an optional field have to be handled, and the PEP 604 one is the
    # common case: every `X | None` in this codebase resolves to `types.UnionType`, whose
    # origin is NOT `typing.Union`.
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(hint) if a is not type(None)]
        if value is None:
            return None
        if len(args) != 1:
            raise SerdeError(f"Cannot decode {value!r} into {hint}.")
        return _decode(value, args[0])

    if origin in (tuple, list):
        args = get_args(hint)
        item_hint = args[0] if args else Any
        decoded = [_decode(v, item_hint) for v in value]
        return tuple(decoded) if origin is tuple else decoded

    if origin in (dict, Mapping):
        args = get_args(hint)
        value_hint = args[1] if len(args) == 2 else Any
        return {k: _decode(v, value_hint) for k, v in value.items()}

    if hint is datetime:
        if not isinstance(value, str):
            raise SerdeError(f"Expected an ISO string for datetime, got {type(value).__name__}.")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise SerdeError(f"{value!r} is not timezone-aware.")
        return parsed

    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(value)

    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        if not isinstance(value, Mapping):
            raise SerdeError(f"Expected a mapping for {hint.__name__}, got {type(value).__name__}.")
        return _decode_dataclass(value, hint)

    if isinstance(hint, type) and isinstance(value, hint):
        return value
    if hint is float and isinstance(value, int):
        return float(value)
    if not isinstance(hint, type):
        return value
    raise SerdeError(f"Cannot decode {value!r} into {hint}.")


def _decode_dataclass(payload: Mapping[str, Any], hint: Any) -> Any:
    fields = dataclasses.fields(hint)
    hints = get_type_hints(hint)
    expected = {f.name for f in fields}
    provided = set(payload)

    unknown = provided - expected
    if unknown:
        raise SerdeError(
            f"{hint.__name__} payload carries unknown field(s) {sorted(unknown)}. A field this "
            f"build does not know about must not be discarded silently."
        )
    missing = expected - provided
    if missing:
        raise SerdeError(
            f"{hint.__name__} payload is missing field(s) {sorted(missing)}. Defaulting them "
            f"would reconstruct a record that was never written."
        )

    # A field annotated `str` whose default is an Enum member holds an enum at runtime.
    # `AcknowledgementToken.state` is exactly that: `state: str = TokenState.ACTIVE`.
    enum_defaults = {
        f.name: type(f.default)
        for f in fields
        if f.default is not dataclasses.MISSING and isinstance(f.default, Enum)
    }

    kwargs: dict[str, Any] = {}
    for name in expected:
        raw = payload[name]
        if name in enum_defaults and hints[name] is str:
            kwargs[name] = enum_defaults[name](raw)
        else:
            kwargs[name] = _decode(raw, hints[name])
    return hint(**kwargs)


def dumps(value: Any) -> dict[str, Any]:
    """Serialise a record into a JSON-shaped dict, refusing anything lossy."""
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise SerdeError(f"dumps expects a dataclass, got {type(value).__name__}.")
    return encoded


def loads(payload: Mapping[str, Any], hint: Any) -> Any:
    """Reconstruct a record, refusing an unknown or missing field."""
    if not (isinstance(hint, type) and dataclasses.is_dataclass(hint)):
        raise SerdeError(f"loads expects a dataclass type, got {hint!r}.")
    return _decode_dataclass(payload, hint)

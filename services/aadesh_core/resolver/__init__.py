"""Deterministic obligation resolution. No model, no network, no clock read."""

from __future__ import annotations

from aadesh_core.resolver.operators import OPERATORS, apply_operator
from aadesh_core.resolver.resolver import resolve_obligations
from aadesh_core.resolver.serialization import resolution_to_dict

__all__ = ["OPERATORS", "apply_operator", "resolution_to_dict", "resolve_obligations"]

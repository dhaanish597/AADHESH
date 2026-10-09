"""The Aadesh local web API: a thin adapter over the deterministic core."""

from __future__ import annotations

__all__ = ["serve"]


def serve(*args, **kwargs):  # pragma: no cover - convenience re-export
    from aadesh_web.server import serve as _serve

    return _serve(*args, **kwargs)

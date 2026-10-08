"""Grounding: refusal of anything the model was not given.

The deterministic core supplies the facts. This module checks that the model's answer stayed
inside them. Four failures are detectable without reading the prose for meaning, which is what
makes this a check rather than a judgement:

  * **A citation that was not supplied.** Law that Aadesh cannot trace is fabricated law.
  * **A source hash that was not supplied.** A hash is the proof a quote is real; invent one
    and the quote becomes unverifiable. Hashes are also scanned for in prose, not just the
    structured references.
  * **A stage that differs from the engine's.** The model may echo the official and implied
    stage; it may not change either, because a changed stage is an activation it has no power
    to authorise.
  * **A replay status that differs from the engine's.** A historical replay may not be
    presented as current.

Everything found here is returned, not raised, so the caller can record exactly what the model
attempted and fall back to the deterministic text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aadesh_core.explanation.context import ExplanationRequest
from aadesh_core.explanation.response import ExplanationResponse

#: A SHA-256 rendered as hex. Used to catch an invented hash in free text.
_HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")


@dataclass(frozen=True, slots=True)
class UnsupportedReference:
    """A specific way the model went beyond what it was given."""

    kind: str
    detail: str


def check_grounding(
    response: ExplanationResponse, *, request: ExplanationRequest
) -> list[UnsupportedReference]:
    """Return every reference in `response` that is not grounded in `request`."""
    unsupported: list[UnsupportedReference] = []
    allowed_keys = request.allowed_citation_keys
    allowed_hashes = request.allowed_source_hashes

    for reference in response.source_references:
        key = (reference.source_doc, reference.page)
        if key not in allowed_keys:
            unsupported.append(
                UnsupportedReference(
                    kind="unknown-citation",
                    detail=(
                        f"Cites {reference.source_doc!r} page {reference.page}, which was not "
                        f"supplied. The model may only cite sources the engine computed."
                    ),
                )
            )
            continue
        if reference.source_hash is not None and reference.source_hash not in allowed_hashes:
            unsupported.append(
                UnsupportedReference(
                    kind="invented-source-hash",
                    detail=(
                        f"States source hash {reference.source_hash[:12]}... for "
                        f"{reference.source_doc!r}, which does not match any supplied source."
                    ),
                )
            )

    for found in _HASH_RE.findall(response.text):
        if found not in allowed_hashes:
            unsupported.append(
                UnsupportedReference(
                    kind="invented-source-hash",
                    detail=(
                        f"States source hash {found[:12]}... in prose, which was not supplied."
                    ),
                )
            )

    if response.official_stage != request.official_stage:
        unsupported.append(
            UnsupportedReference(
                kind="stage-contradiction",
                detail=(
                    f"Echoes official stage {response.official_stage!r}, but the engine "
                    f"determined {request.official_stage!r}. The model may not change the stage."
                ),
            )
        )
    if response.implied_stage != request.implied_stage:
        unsupported.append(
            UnsupportedReference(
                kind="stage-contradiction",
                detail=(
                    f"Echoes implied stage {response.implied_stage!r}, but the engine "
                    f"determined {request.implied_stage!r}. The model may not change the stage."
                ),
            )
        )
    if response.replay_status != request.mode:
        unsupported.append(
            UnsupportedReference(
                kind="replay-contradiction",
                detail=(
                    f"States replay status {response.replay_status!r}, but the engine "
                    f"determined {request.mode!r}. A replay is not current state."
                ),
            )
        )

    return unsupported


__all__ = ["UnsupportedReference", "check_grounding"]

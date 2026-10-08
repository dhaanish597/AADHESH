"""Extract a structured explanation from model text.

Both the Bedrock and Strands adapters receive text that is *supposed* to be a single JSON
object. Models sometimes wrap it in a Markdown code fence despite being asked not to, so the
fence is stripped here. Nothing else is inferred: if the remaining text is not valid JSON, or
does not match the response schema, parsing raises and the caller falls back to deterministic
text. Guessing at a malformed answer is exactly the failure this layer exists to avoid.
"""

from __future__ import annotations

import json

from aadesh_core.explanation import ExplanationResponse


def strip_code_fence(text: str) -> str:
    """Remove a leading/trailing Markdown fence if the model added one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    inner = stripped[3:]
    if inner.startswith("json"):
        inner = inner[4:]
    if inner.endswith("```"):
        inner = inner[:-3]
    return inner.strip()


def parse_response(text: str, *, model_metadata: dict[str, str]) -> ExplanationResponse:
    """Parse one model reply into a validated `ExplanationResponse`.

    Raises `ValueError` (via `json` or `from_payload`) when the reply is not usable, which the
    service treats as EXPLANATION_UNAVAILABLE rather than fabricating an explanation.
    """
    stripped = strip_code_fence(text)
    if not stripped:
        raise ValueError("Explanation model returned empty text")
    payload = json.loads(stripped)
    return ExplanationResponse.from_payload(payload, model_metadata=model_metadata)


__all__ = ["parse_response", "strip_code_fence"]

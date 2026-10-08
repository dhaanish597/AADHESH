"""Explanation adapters: the model-backed half of the explanation layer.

`BedrockExplanationModel` and `StrandsExplanationModel` satisfy
`aadesh_core.ports.explanation.ExplanationModel`. `FakeExplanationModel` satisfies the same
port for tests, offline, with no AWS or Strands. All three are optional: the deterministic
text in `aadesh_core.explanation.deterministic` is the fallback and always exists.
"""

from __future__ import annotations

from aadesh_adapters.explain.bedrock import DEFAULT_MODEL_ID, BedrockExplanationModel
from aadesh_adapters.explain.fake import FakeExplanationModel
from aadesh_adapters.explain.parsing import parse_response, strip_code_fence
from aadesh_adapters.explain.strands import StrandsExplanationModel

__all__ = [
    "DEFAULT_MODEL_ID",
    "BedrockExplanationModel",
    "FakeExplanationModel",
    "StrandsExplanationModel",
    "parse_response",
    "strip_code_fence",
]

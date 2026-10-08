"""Amazon Bedrock, as an explanation adapter behind the `ExplanationModel` port.

The domain never imports boto3 or this module. A caller wires it in at the composition root,
and `ExplanationService` treats it as entirely optional: if Bedrock is unreachable, the
deterministic text is shown and Aadesh still resolves, authorizes and seals.

Two properties are deliberate:

  * **boto3 is imported lazily.** The default path builds a real `bedrock-runtime` client, but
    only when the adapter is actually constructed with no injected client. A test (or an
    environment without the AWS extra) can pass a fake client and never load boto3 at all.

  * **The model has no tools and no authority.** The adapter sends text and reads text back.
    There is no function-calling surface here through which the model could invoke a GRAP
    stage, open or seal a Parchi, authorize a principal, or touch the corpus.
"""

from __future__ import annotations

from typing import Any

from aadesh_adapters.explain.parsing import parse_response
from aadesh_core.errors import ExplanationUnavailable
from aadesh_core.explanation import ExplanationRequest, ExplanationResponse, build_prompt

DEFAULT_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"


class BedrockExplanationModel:
    """Satisfies `ExplanationModel` via the Bedrock Converse API."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model_id: str = DEFAULT_MODEL_ID,
        region_name: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> None:
        self._client = client if client is not None else _default_client(region_name)
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._temperature = temperature

    def explain(self, *, request: ExplanationRequest) -> ExplanationResponse | None:
        prompt = build_prompt(request)
        response = self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": self._temperature},
        )
        text = _extract_text(response)
        if not text:
            return None
        return parse_response(
            text, model_metadata={"provider": "bedrock", "model_id": self._model_id}
        )


def _default_client(region_name: str | None) -> Any:
    try:
        # Imported lazily so the default test path never needs the AWS SDK.
        import boto3
    except ImportError as exc:  # pragma: no cover - only when the AWS extra is absent
        raise ExplanationUnavailable(
            "The AWS extra is not installed, so a Bedrock client cannot be created. Install "
            "`.[aws]`, or inject a client for tests."
        ) from exc
    return boto3.client("bedrock-runtime", region_name=region_name)


def _extract_text(response: Any) -> str:
    """Read the first text block of a Converse response, or '' if there is none."""
    try:
        content = response["output"]["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ExplanationUnavailable(f"Unexpected Bedrock response shape: {exc}") from exc
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            return block["text"]
    return ""


__all__ = ["DEFAULT_MODEL_ID", "BedrockExplanationModel"]

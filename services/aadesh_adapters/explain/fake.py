"""A deterministic explanation model for tests. TEST ENVIRONMENTS ONLY.

Tests must not need AWS credentials, a network, Bedrock, or Strands. This fake stands in for
all of them and can be configured to simulate every failure mode the real layer must survive:

    FakeExplanationModel(response=...)          # a faithful explanation
    FakeExplanationModel(response=hallucinated) # an unsupported one, to prove it is refused
    FakeExplanationModel(error=RuntimeError())  # a provider outage
    FakeExplanationModel(malformed=True)        # structured output that will not parse
    FakeExplanationModel(responder=lambda r: ...)  # per-request behaviour

It records every request it sees, so a test can assert the raw acknowledgement token or other
personal data was never sent.

It refuses to construct outside AADESH_ENV=test, mirroring `AllowAllTestOnly`: production must
never depend on it.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from aadesh_core.errors import TestOnlyComponentInProduction
from aadesh_core.explanation import ExplanationRequest, ExplanationResponse

REQUIRED_ENV = "test"

Responder = Callable[[ExplanationRequest], ExplanationResponse | None]


class FakeExplanationModel:
    """A configurable, offline stand-in for Bedrock/Strands."""

    def __init__(
        self,
        *,
        response: ExplanationResponse | None = None,
        error: BaseException | None = None,
        malformed: bool = False,
        responder: Responder | None = None,
    ) -> None:
        env = os.environ.get("AADESH_ENV")
        if env != REQUIRED_ENV:
            raise TestOnlyComponentInProduction(
                f"FakeExplanationModel produces canned explanations and must never run outside "
                f"tests. AADESH_ENV is {env!r}, expected {REQUIRED_ENV!r}. "
                f"Use BedrockExplanationModel or StrandsExplanationModel instead."
            )
        self._response = response
        self._error = error
        self._malformed = malformed
        self._responder = responder
        self.calls: list[ExplanationRequest] = []

    @property
    def last_request(self) -> ExplanationRequest | None:
        return self.calls[-1] if self.calls else None

    def explain(self, *, request: ExplanationRequest) -> ExplanationResponse | None:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        if self._malformed:
            raise ValueError("simulated malformed structured output")
        if self._responder is not None:
            return self._responder(request)
        return self._response


__all__ = ["FakeExplanationModel"]

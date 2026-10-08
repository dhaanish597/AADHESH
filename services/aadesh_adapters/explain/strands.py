"""Strands, kept as a read-only orchestration wrapper behind the `ExplanationModel` port.

Strands is an agent framework. Handing a compliance system's explanation layer an *agent* is
one step away from handing it tools, so this adapter pins the boundary explicitly:

  * The agent is constructed with **no tools**. There is no tool through which it could trigger
    a Standing Order, issue a halt, create/acknowledge/seal a Parchi, authorize a principal,
    modify CAQM source data, or modify resolver rules.
  * The adapter only ever sends the structured prompt and reads text back. It never applies a
    result to any state.

Because Strands is not installed in the default environment, the real construction lives behind
`from_strands`, which imports Strands lazily and raises `ExplanationUnavailable` when it is
absent. The rest of Aadesh does not depend on Strands existing: tests inject an agent-shaped
callable, and a deployment without Strands uses the Bedrock adapter or the deterministic text.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aadesh_adapters.explain.parsing import parse_response
from aadesh_core.errors import ExplanationUnavailable
from aadesh_core.explanation import (
    SYSTEM_PROMPT,
    ExplanationRequest,
    ExplanationResponse,
    build_prompt,
)

AgentCallable = Callable[[str], str]


class StrandsExplanationModel:
    """Satisfies `ExplanationModel` by delegating to a tool-free Strands agent."""

    def __init__(self, *, agent: Any, system_prompt: str = SYSTEM_PROMPT) -> None:
        if agent is None:
            raise ExplanationUnavailable("A Strands agent is required; none was provided.")
        self._agent = agent
        self._system_prompt = system_prompt

    @classmethod
    def from_strands(
        cls, *, model: Any | None = None, system_prompt: str = SYSTEM_PROMPT
    ) -> StrandsExplanationModel:
        """Build a real Strands agent with NO tools, or raise `ExplanationUnavailable`.

        The absence of a `tools=` argument is the security property: this agent can explain and
        nothing else. If Strands is not installed, the caller falls back to deterministic text.
        """
        try:
            from strands import Agent
        except ImportError as exc:  # pragma: no cover - exercised only where Strands is absent
            raise ExplanationUnavailable(
                "Strands is not installed, so no Strands agent can be created. Install strands-"
                "agents, or use the Bedrock adapter or deterministic text."
            ) from exc
        agent = Agent(model=model, system_prompt=system_prompt)
        return cls(agent=agent, system_prompt=system_prompt)

    def explain(self, *, request: ExplanationRequest) -> ExplanationResponse | None:
        prompt = build_prompt(request)
        text = self._invoke(prompt)
        if not text:
            return None
        return parse_response(text, model_metadata={"provider": "strands"})

    def _invoke(self, prompt: str) -> str:
        agent = self._agent
        if hasattr(agent, "invoke"):
            result = agent.invoke(prompt)
        elif callable(agent):
            result = agent(prompt)
        else:
            raise ExplanationUnavailable(
                "The supplied Strands agent is neither callable nor has an `invoke` method."
            )
        if isinstance(result, str):
            return result
        return str(result)


__all__ = ["StrandsExplanationModel"]

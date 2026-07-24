"""Per-node LLM sampling config — replaces the single global RETRY_TEMPERATURES.

Plain Python dict, not YAML: six nodes don't need a second config format, and
keeping it in code means it's reviewed/diffed like everything else it sits
next to (graph.py reads it directly).
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas import AgentName


@dataclass(frozen=True)
class NodeLLMConfig:
    model: str | None = None
    temperature_ladder: tuple[float, ...] = (0.0, 0.4, 0.7)
    top_p: float | None = None
    # Cap the completion budget. Left unset, providers (e.g. OpenRouter) default
    # to the model's max ceiling (tens of thousands of tokens), which is both
    # wasteful and can trip credit/affordability limits — an extracted structured
    # JSON for one document never needs that much. Tune per node if a very long
    # output is ever truncated.
    max_tokens: int | None = 8192
    # Per-agent confidence floor — AgentValidationResult.pass_rate (fraction of
    # fields that passed span-grounded validation) must reach this to stop
    # retrying. 1.0 (default) preserves the original behavior: every field
    # must pass. Lower it per node to accept a partial pass rather than
    # burning all retries chasing one stubborn field.
    confidence_threshold: float = 1.0


DEFAULT_NODE_LLM_CONFIG: dict[AgentName, NodeLLMConfig] = {
    AgentName.METADATA: NodeLLMConfig(),
    AgentName.FACTS: NodeLLMConfig(),
    AgentName.STATUTE: NodeLLMConfig(),
    AgentName.PETITIONER: NodeLLMConfig(),
    AgentName.RESPONDENT: NodeLLMConfig(),
    AgentName.EVIDENCE: NodeLLMConfig(),
}

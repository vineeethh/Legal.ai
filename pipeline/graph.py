"""LangGraph supervisor — fan-out/barrier/validate/retry/assemble/score/route.

Matches docs/architecture/data_flow.md's Orchestration section:
  - Fan-out: the 6 extraction agents are independent nodes with no edges between
    them, so LangGraph's Pregel executor runs them concurrently.
  - Barrier: the `assemble` node has an incoming edge from all 6 agents, so it
    only runs once every agent (including its retries) has finished.
  - Retries are blind: only `temperature` varies across attempts (0 -> 0.4 -> 0.7);
    no validator feedback is ever passed back into a retried agent's prompt.
  - Checkpointing: MemorySaver persists state per step so a crash mid-run resumes
    rather than reprocessing the document from scratch. Swap for a Postgres
    checkpointer (langgraph-checkpoint-postgres) for a multi-process deployment.
"""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import Field

from schemas import AgentName, AgentValidationResult, PipelineState, ProcessingMetadata

from .agents import arguments as arguments_agent
from .agents import evidence as evidence_agent
from .agents import facts as facts_agent
from .agents import metadata as metadata_agent
from .agents import response as response_agent
from .agents import statute as statute_agent
from .chunking import Chunk, chunk_document
from .confidence import compute_confidence
from .config import get_settings
from .docling_parse import parse_pdf
from .embeddings import JudgmentChunkIndex
from .router import apply_retrieval_fallback, route_document
from .statute_verification import verify_statute_output
from .validation import validate_agent_output

RETRY_TEMPERATURES = (0.0, 0.4, 0.7)

_AGENT_RUNNERS = {
    AgentName.METADATA: metadata_agent.run,
    AgentName.FACTS: facts_agent.run,
    AgentName.STATUTE: statute_agent.run,
    AgentName.PETITIONER: arguments_agent.run_petitioner,
    AgentName.RESPONDENT: arguments_agent.run_respondent,
    AgentName.EVIDENCE: evidence_agent.run,
}

# AgentName.value doesn't always match the PipelineState field name (e.g.
# STATUTE.value == "statute" but the field is "statutes") — map explicitly
# rather than assuming they line up.
_AGENT_STATE_FIELD = {
    AgentName.METADATA: "metadata",
    AgentName.FACTS: "facts",
    AgentName.STATUTE: "statutes",
    AgentName.PETITIONER: "petitioner",
    AgentName.RESPONDENT: "respondent",
    AgentName.EVIDENCE: "evidence",
}


class GraphState(PipelineState):
    """PipelineState with merge reducers on the dict fields multiple agent
    nodes write to concurrently. Plain last-write-wins (the default for a
    field with no reducer) would drop updates when two nodes finish in the
    same Pregel step — see schemas/state.py's reducer note."""

    validations: Annotated[dict, operator.or_] = Field(default_factory=dict)
    retry_counts: Annotated[dict, operator.or_] = Field(default_factory=dict)


class RunContext:
    """Non-serialized run-scoped data (chunks, the ephemeral embedding index)
    kept outside PipelineState — graph state must stay checkpoint-serializable,
    and re-embedding a document's chunks doesn't belong in persisted state."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.chunks_by_id = {c.chunk_id: c for c in chunks}
        self._index: JudgmentChunkIndex | None = None

    @property
    def index(self) -> JudgmentChunkIndex:
        if self._index is None:
            self._index = JudgmentChunkIndex(self.chunks)
        return self._index


def _run_agent_with_retries(agent: AgentName, state: PipelineState, ctx: RunContext):
    """Runs one agent, validates, and blindly retries (temperature only) up to
    settings.max_retries. Returns (output, AgentValidationResult, retry_count)."""
    settings = get_settings()
    routed = apply_retrieval_fallback(agent, state.agent_inputs[agent], ctx.index)
    chunks = [ctx.chunks_by_id[cid] for cid in routed.chunk_ids if cid in ctx.chunks_by_id]
    runner = _AGENT_RUNNERS[agent]

    output = validation = None
    for attempt in range(settings.max_retries + 1):
        temperature = RETRY_TEMPERATURES[min(attempt, len(RETRY_TEMPERATURES) - 1)]
        output = runner(chunks, temperature=temperature)
        validation = validate_agent_output(agent, output, ctx.chunks_by_id, attempt=attempt)
        if validation.overall.value == "pass":
            return output, validation, attempt

    # Retries exhausted: return the last attempt: per design a still-failing
    # field surfaces via `validations` (and is reflected in confidence) rather
    # than blocking the run — the record is written with review_decision
    # routed to human review by the confidence engine, not silently dropped.
    return output, validation, settings.max_retries


def build_graph(ctx: RunContext) -> StateGraph:
    graph = StateGraph(GraphState)

    def make_agent_node(agent: AgentName):
        def node(state: GraphState) -> dict:
            output, validation, retries = _run_agent_with_retries(agent, state, ctx)
            return {
                _AGENT_STATE_FIELD[agent]: output,
                "validations": {agent: validation},
                "retry_counts": {agent: retries},
            }

        return node

    for agent in _AGENT_RUNNERS:
        graph.add_node(agent.value, make_agent_node(agent))
        graph.add_edge("__start__", agent.value)

    def assemble_node(state: GraphState) -> dict:
        statutes_verified = verify_statute_output(
            state.statutes, as_of_date=state.metadata.decision_date.value
        )
        confidence = compute_confidence(
            metadata=state.metadata,
            facts=state.facts,
            statutes=statutes_verified,
            petitioner=state.petitioner,
            respondent=state.respondent,
            evidence=state.evidence,
            validations=state.validations,
        )
        processing = ProcessingMetadata(
            document_id=state.document_id,
            llm_model=get_settings().llm_model,
            retry_counts={k.value: v for k, v in state.retry_counts.items()},
        )
        result = response_agent.assemble(
            metadata=state.metadata,
            facts=state.facts,
            statutes=statutes_verified,
            petitioner=state.petitioner,
            respondent=state.respondent,
            evidence=state.evidence,
            confidence=confidence,
            processing=processing,
        )
        return {"statutes": statutes_verified, "confidence": confidence, "result": result}

    graph.add_node("assemble", assemble_node)
    for agent in _AGENT_RUNNERS:
        graph.add_edge(agent.value, "assemble")
    graph.add_edge("assemble", END)

    return graph


def run_document(document_id: str, source_path: str, *, run_config: dict | None = None) -> GraphState:
    """Parse + chunk + route a PDF, then run it through the compiled LangGraph
    supervisor. `run_config` is typically `observability.traced_run_config(...)`
    to attach Langfuse session/user/tags to the run."""
    parsed = parse_pdf(source_path)
    chunks = chunk_document(parsed)
    ctx = RunContext(chunks)

    initial_state = GraphState(
        document_id=document_id,
        source_path=str(source_path),
        chunk_count=len(chunks),
        ocr_used=parsed.ocr_used,
        agent_inputs=route_document(parsed, chunks),
    )

    graph = build_graph(ctx).compile(checkpointer=MemorySaver())
    config = dict(run_config or {})
    config.setdefault("configurable", {})["thread_id"] = document_id

    result = graph.invoke(initial_state, config=config)
    return GraphState.model_validate(result)

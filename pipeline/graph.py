"""LangGraph supervisor — fan-out/validate/retry-as-cycle/assemble/score/route.

Matches docs/architecture/data_flow.md's Orchestration section:
  - Fan-out: the 6 extraction agents are independent branches with no edges
    between them, so LangGraph's Pregel executor runs them concurrently.
  - Retry as a real graph cycle: each agent node (one LLM attempt) is followed
    by its own `<agent>_confidence` node, which scores the attempt
    (AgentValidationResult.pass_rate against NodeLLMConfig.confidence_threshold,
    pipeline/llm_config.py) and either loops back to the agent node (a visible
    cycle in the compiled graph / graph.png) or proceeds to `assemble`. Retries
    are still blind — only `temperature` varies across attempts; no validator
    feedback is passed back into the retried prompt.
  - Barrier: `assemble` has an incoming edge (via each agent's confidence node)
    from all 6 branches, so it only runs once every agent — including its
    retries — has finished.
  - Document-level scoring is its own node (`confidence`, after `assemble`),
    separate from assembly, so it's visible in the graph independent of the
    per-agent confidence nodes above.
  - Checkpointing: PostgresSaver persists state per step so a crash mid-run
    resumes rather than reprocessing the document from scratch, and so a
    paused (interrupted) run can be resumed from a later process.
  - Human review: only `human_required` (score < 0.80) pauses the graph via
    `interrupt()` — `auto_save`/`needs_review` persist as before.
"""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Callable

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt
from pydantic import Field

from schemas import (
    AgentName,
    PipelineState,
    ProcessingMetadata,
    ReviewDecision,
    StructuredJudgment,
)

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
from .fallback import apply_fallback
from .injection_screen import scan_chunks
from .llm_config import DEFAULT_NODE_LLM_CONFIG
from .pdf_safety import PdfSafetyError, scan_pdf_safety
from .router import apply_retrieval_fallback, route_document
from .statute_verification import verify_statute_output
from .validation import validate_agent_output

HUMAN_REVIEW_NODE = "human_review"

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
    # "retry" | "done" per agent, written by that agent's confidence node and
    # read by the conditional edge routing back to the agent node (a cycle)
    # or forward to assemble. Kept as an explicit signal rather than having
    # the routing function re-derive it from retry_counts — retry_counts
    # alone is ambiguous (the post-increment value looks the same whether a
    # retry was just scheduled or retries were just exhausted).
    retry_decision: Annotated[dict, operator.or_] = Field(default_factory=dict)
    # Written by each agent's confidence node only once that agent is truly
    # finished (pass, or retries exhausted) — never on a "retry" outcome.
    # `fan_in_gate` is the only thing that reads this: LangGraph does NOT wait
    # for all of a node's structural predecessors before running it — a node
    # with multiple incoming edges fires on EVERY trigger it receives, not
    # once-all-arrived (confirmed empirically: with a bare `assemble` node
    # fed by 6 conditional edges, it ran prematurely using an agent's
    # still-mid-retry output, sometimes more than once). `agents_done` plus
    # `fan_in_gate` is the explicit manual barrier that replaces the implicit
    # one the original single-node-per-agent design got "for free" only
    # because every agent finished within a single Pregel superstep.
    agents_done: Annotated[dict, operator.or_] = Field(default_factory=dict)


class RunContext:
    """Non-serialized run-scoped data (chunks, the ephemeral embedding index)
    kept outside PipelineState — graph state must stay checkpoint-serializable,
    and re-embedding a document's chunks doesn't belong in persisted state.

    Starts empty and is populated by the `parse_and_chunk` node — parsing
    happens *inside* the graph (after the `pdf_safety_gate` node) so an unsafe
    PDF is never handed to Docling, not even to build this context."""

    def __init__(self, source_path: str):
        self.source_path = source_path
        self.chunks: list[Chunk] = []
        self.chunks_by_id: dict[str, Chunk] = {}
        self._index: JudgmentChunkIndex | None = None

    def set_chunks(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.chunks_by_id = {c.chunk_id: c for c in chunks}
        self._index = None

    @property
    def index(self) -> JudgmentChunkIndex:
        if self._index is None:
            self._index = JudgmentChunkIndex(self.chunks)
        return self._index


def build_graph(ctx: RunContext) -> StateGraph:
    graph = StateGraph(GraphState)

    def pdf_safety_gate_node(state: GraphState) -> dict:
        result = scan_pdf_safety(state.source_path)
        return {"pdf_safety_reasons": result.reasons}

    def parse_and_chunk_node(state: GraphState) -> dict:
        parsed = parse_pdf(state.source_path)
        chunks = chunk_document(parsed)
        ctx.set_chunks(chunks)
        return {
            "chunk_count": len(chunks),
            "ocr_used": parsed.ocr_used,
            "agent_inputs": route_document(parsed, chunks),
        }

    def injection_screen_node(state: GraphState) -> dict:
        return {"injection_matches": scan_chunks(ctx.chunks)}

    def rejected_node(state: GraphState) -> dict:
        # Terminal node for an unsafe PDF — run_document() raises PdfSafetyError
        # once the graph finishes, reading state.pdf_safety_reasons. No agent
        # ever runs and Docling never touches the file.
        return {}

    def route_after_safety(state: GraphState) -> str:
        return "unsafe" if state.pdf_safety_reasons else "safe"

    graph.add_node("pdf_safety_gate", pdf_safety_gate_node)
    graph.add_node("parse_and_chunk", parse_and_chunk_node)
    graph.add_node("injection_screen", injection_screen_node)
    graph.add_node("rejected", rejected_node)
    graph.add_edge("__start__", "pdf_safety_gate")
    graph.add_conditional_edges(
        "pdf_safety_gate", route_after_safety, {"safe": "parse_and_chunk", "unsafe": "rejected"}
    )
    graph.add_edge("parse_and_chunk", "injection_screen")
    graph.add_edge("rejected", END)

    def make_agent_node(agent: AgentName):
        """Runs exactly ONE attempt at temperature ladder[attempt] — no retry
        loop in here. `attempt` comes from state.retry_counts, written by
        this agent's confidence node; a fresh run starts at 0."""

        def node(state: GraphState) -> dict:
            node_cfg = DEFAULT_NODE_LLM_CONFIG[agent]
            attempt = state.retry_counts.get(agent, 0)
            routed = apply_retrieval_fallback(agent, state.agent_inputs[agent], ctx.index)
            chunks = [ctx.chunks_by_id[cid] for cid in routed.chunk_ids if cid in ctx.chunks_by_id]
            runner = _AGENT_RUNNERS[agent]
            ladder = node_cfg.temperature_ladder
            temperature = ladder[min(attempt, len(ladder) - 1)]
            output = runner(
                chunks,
                temperature=temperature,
                model=node_cfg.model,
                top_p=node_cfg.top_p,
                max_tokens=node_cfg.max_tokens,
            )
            return {_AGENT_STATE_FIELD[agent]: output}

        return node

    def make_confidence_node(agent: AgentName):
        """Scores the agent's last attempt (AgentValidationResult.pass_rate —
        deterministic, not self-reported by the LLM) against the node's
        confidence_threshold. Below threshold with retries left: schedules a
        retry (loops back to this agent's own node — a real graph cycle, not
        a hidden Python loop). Below threshold with retries exhausted:
        apply_fallback() prunes the still-failing fields rather than shipping
        them as an unverified guess — 'None over guessing' applied to the
        retry-exhausted case, not just the first attempt."""

        def node(state: GraphState) -> dict:
            output = getattr(state, _AGENT_STATE_FIELD[agent])
            attempt = state.retry_counts.get(agent, 0)
            validation = validate_agent_output(agent, output, ctx.chunks_by_id, attempt=attempt)
            settings = get_settings()
            node_cfg = DEFAULT_NODE_LLM_CONFIG[agent]
            below_threshold = validation.pass_rate < node_cfg.confidence_threshold
            will_retry = below_threshold and attempt < settings.max_retries

            updates: dict = {
                "validations": {agent: validation},
                "retry_decision": {agent: "retry" if will_retry else "done"},
                "retry_counts": {agent: attempt + 1 if will_retry else attempt},
            }
            if not will_retry:
                updates["agents_done"] = {agent: True}
            if below_threshold and not will_retry:
                updates[_AGENT_STATE_FIELD[agent]] = apply_fallback(output, validation)
            return updates

        return node

    def make_route_after_confidence(agent: AgentName):
        def route(state: GraphState) -> str:
            return state.retry_decision[agent]

        return route

    def fan_in_gate_node(state: GraphState) -> dict:
        # No-op — exists only as a routing point. May run multiple times over
        # the course of one document (once per agent that finishes), because
        # LangGraph fires a multi-predecessor node on every trigger it
        # receives rather than waiting for all predecessors — see the
        # `agents_done` field comment on GraphState. Only the invocation where
        # every agent has finished actually proceeds past route_after_fan_in.
        return {}

    def route_after_fan_in(state: GraphState) -> str:
        return "ready" if len(state.agents_done) == len(_AGENT_RUNNERS) else "wait"

    graph.add_node("fan_in_gate", fan_in_gate_node)
    graph.add_conditional_edges("fan_in_gate", route_after_fan_in, {"ready": "assemble", "wait": END})

    for agent in _AGENT_RUNNERS:
        confidence_node_name = f"{agent.value}_confidence"
        graph.add_node(agent.value, make_agent_node(agent))
        graph.add_node(confidence_node_name, make_confidence_node(agent))
        graph.add_edge("injection_screen", agent.value)
        graph.add_edge(agent.value, confidence_node_name)
        graph.add_conditional_edges(
            confidence_node_name,
            make_route_after_confidence(agent),
            {"retry": agent.value, "done": "fan_in_gate"},
        )

    def assemble_node(state: GraphState) -> dict:
        statutes_verified = verify_statute_output(
            state.statutes, as_of_date=state.metadata.decision_date.value
        )
        return {"statutes": statutes_verified}

    def document_confidence_node(state: GraphState) -> dict:
        confidence = compute_confidence(
            metadata=state.metadata,
            facts=state.facts,
            statutes=state.statutes,
            petitioner=state.petitioner,
            respondent=state.respondent,
            evidence=state.evidence,
            validations=state.validations,
        )
        if state.injection_matches and confidence.decision == ReviewDecision.AUTO_SAVE:
            # Guardrail floor: a document with flagged chunks never auto-saves,
            # regardless of how clean the extraction otherwise looks — see
            # pipeline/injection_screen.py.
            confidence = confidence.model_copy(update={"decision": ReviewDecision.NEEDS_REVIEW})
        processing = ProcessingMetadata(
            document_id=state.document_id,
            llm_model=get_settings().llm_model,
            retry_counts={k.value: v for k, v in state.retry_counts.items()},
        )
        result = response_agent.assemble(
            metadata=state.metadata,
            facts=state.facts,
            statutes=state.statutes,
            petitioner=state.petitioner,
            respondent=state.respondent,
            evidence=state.evidence,
            confidence=confidence,
            processing=processing,
        )
        return {"confidence": confidence, "result": result}

    def human_review_node(state: GraphState) -> dict:
        flagged_fields = [
            {
                "agent": agent.value,
                "field_path": f.field_path,
                "status": f.status.value,
                "reason": f.reason,
            }
            for agent, validation in state.validations.items()
            for f in validation.fields
            if f.status.value == "fail"
        ]
        payload = {
            "document_id": state.document_id,
            "decision": state.confidence.decision.value,
            "confidence_score": state.confidence.score,
            "flagged_fields": flagged_fields,
            "result_preview": state.result.model_dump(mode="json"),
        }
        decision = interrupt(payload)

        action = decision.get("action")
        if action == "reject":
            return {"result": state.result.model_copy(update={"review_decision": ReviewDecision.HUMAN_REQUIRED})}
        if action == "edit":
            patched = state.result.model_dump(mode="json")
            patched.update(decision.get("patches") or {})
            return {"result": StructuredJudgment.model_validate(patched)}
        return {}  # approve: keep the assembled result as-is

    def route_after_confidence(state: GraphState) -> str:
        return "review" if state.confidence.decision == ReviewDecision.HUMAN_REQUIRED else "save"

    graph.add_node("assemble", assemble_node)
    graph.add_node("confidence", document_confidence_node)
    graph.add_node(HUMAN_REVIEW_NODE, human_review_node)
    graph.add_edge("assemble", "confidence")
    graph.add_conditional_edges("confidence", route_after_confidence, {"save": END, "review": HUMAN_REVIEW_NODE})
    graph.add_edge(HUMAN_REVIEW_NODE, END)

    return graph


def run_document(
    document_id: str,
    source_path: str,
    *,
    run_config: dict | None = None,
    on_human_review: Callable[[dict], dict] | None = None,
) -> tuple[GraphState, dict | None]:
    """Parse + chunk + route a PDF, then run it through the compiled LangGraph
    supervisor. `run_config` is typically `observability.traced_run_config(...)`
    to attach Langfuse session/user/tags to the run.

    `on_human_review`, if given, is called with the human_review interrupt
    payload whenever confidence routes a run to `human_required`; it must
    return the resume decision dict (`{"action": "approve"|"reject"|"edit", ...}`).
    Returns `(final_state, human_review_decision)` — the decision is None
    unless the run was actually interrupted.

    Raises `PdfSafetyError` if the file fails the structural safety scan —
    the check runs as the graph's first node (`pdf_safety_gate`), before
    `parse_and_chunk` ever calls Docling on the file's bytes.
    """
    ctx = RunContext(str(source_path))

    initial_state = GraphState(document_id=document_id, source_path=str(source_path))

    settings = get_settings()
    config = dict(run_config or {})
    config.setdefault("configurable", {})["thread_id"] = document_id

    with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        graph = build_graph(ctx).compile(checkpointer=checkpointer)

        result = graph.invoke(initial_state, config=config)
        if result.get("pdf_safety_reasons"):
            raise PdfSafetyError(result["pdf_safety_reasons"])

        human_review_decision: dict | None = None

        while graph.get_state(config).next:
            if on_human_review is None:
                raise RuntimeError(
                    f"Run {document_id} paused for human review but no on_human_review "
                    "callback was given to run_document()."
                )
            interrupt_payload = graph.get_state(config).tasks[0].interrupts[0].value
            human_review_decision = on_human_review(interrupt_payload)
            result = graph.invoke(Command(resume=human_review_decision), config=config)

    return GraphState.model_validate(result), human_review_decision

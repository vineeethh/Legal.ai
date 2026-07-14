"""Generates the "real graph" sections of docs/architecture/data_flow.md from
the actual compiled StateGraph, prompt registry, and per-node LLM config —
so they can't drift from the code the way the hand-drawn diagram could. Also
writes docs/architecture/graph.png — an actual image, for anyone who'd rather
open a picture than read Mermaid source.

    python -m pipeline.architecture_doc

Regenerates the content between the GRAPH/NODES markers in
docs/architecture/data_flow.md in place; everything else in that file (design
invariants, the broader pipeline overview, known limitations) is untouched.

PNG rendering calls out to the mermaid.ink API (LangGraph's default
draw_mermaid_png() backend) and so needs network access; if that's not
available, the Mermaid block in data_flow.md is still regenerated normally.
"""

from __future__ import annotations

from pathlib import Path

from .agents import response as response_agent
from .graph import HUMAN_REVIEW_NODE, RunContext, _AGENT_RUNNERS, _AGENT_STATE_FIELD, build_graph
from .llm_config import DEFAULT_NODE_LLM_CONFIG
from .prompts import AGENT_PROMPTS

DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "architecture" / "data_flow.md"
PNG_PATH = DOC_PATH.parent / "graph.png"

GRAPH_START, GRAPH_END = "<!-- GRAPH:START -->", "<!-- GRAPH:END -->"
NODES_START, NODES_END = "<!-- NODES:START -->", "<!-- NODES:END -->"


def _compiled_graph():
    ctx = RunContext("placeholder.pdf")
    return build_graph(ctx).compile()


def render_mermaid() -> str:
    return _compiled_graph().get_graph().draw_mermaid()


def render_png() -> bytes:
    return _compiled_graph().get_graph().draw_mermaid_png()


def render_node_table() -> str:
    lines = [
        "| Node | Prompt | Model | Temperature ladder | top_p | max_tokens | Confidence threshold | Writes state field |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for agent in _AGENT_RUNNERS:
        spec = AGENT_PROMPTS[agent]
        cfg = DEFAULT_NODE_LLM_CONFIG[agent]
        prompt_summary = spec.system_prompt.strip().splitlines()[0]
        if spec.is_template:
            prompt_summary += f" _(template, params={spec.template_params})_"
        lines.append(
            f"| `{agent.value}` | {prompt_summary} | {cfg.model or 'settings.llm_model'} "
            f"| {list(cfg.temperature_ladder)} | {cfg.top_p} | {cfg.max_tokens} | — "
            f"| `{_AGENT_STATE_FIELD[agent]}` |"
        )
        lines.append(
            f"| `{agent.value}_confidence` | _(no LLM call — scores AgentValidationResult.pass_rate; "
            f"loops back to `{agent.value}` on retry, else -> assemble)_ | — | — | — | — "
            f"| {cfg.confidence_threshold} | `validations`, `retry_counts`, `retry_decision` |"
        )
    lines.append("| `fan_in_gate` | _(no LLM call — manual barrier; only proceeds to assemble once agents_done covers all 6 agents)_ | — | — | — | — | — | — |")
    lines.append("| `pdf_safety_gate` | _(no LLM call — structural PDF scan, pipeline/pdf_safety.py)_ | — | — | — | — | — | `pdf_safety_reasons` |")
    lines.append("| `parse_and_chunk` | _(no LLM call — Docling parse + chunk, only reached if pdf_safety_gate passes)_ | — | — | — | — | — | `chunk_count`, `ocr_used`, `agent_inputs` |")
    lines.append("| `injection_screen` | _(no LLM call — pattern scan, pipeline/injection_screen.py)_ | — | — | — | — | — | `injection_matches` |")
    lines.append("| `rejected` | _(no LLM call — terminal node for an unsafe PDF)_ | — | — | — | — | — | — |")
    lines.append(f"| `assemble` | _(no LLM call — statute verification only, {response_agent.__name__} assembly happens in \\`confidence\\`)_ | — | — | — | — | — | `statutes` |")
    lines.append("| `confidence` | _(no LLM call — document-level ConfidenceBreakdown + builds the final result)_ | — | — | — | — | — | `confidence`, `result` |")
    lines.append(f"| `{HUMAN_REVIEW_NODE}` | _(no LLM call — interrupt() pauses for a human decision)_ | — | — | — | — | — | `result` |")
    return "\n".join(lines)


def _replace_between(text: str, start_marker: str, end_marker: str, new_body: str) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker)
    return text[:start] + "\n" + new_body + "\n" + text[end:]


def regenerate() -> None:
    text = DOC_PATH.read_text()
    mermaid_block = "```mermaid\n" + render_mermaid() + "\n```"
    text = _replace_between(text, GRAPH_START, GRAPH_END, mermaid_block)
    text = _replace_between(text, NODES_START, NODES_END, render_node_table())
    DOC_PATH.write_text(text)

    try:
        PNG_PATH.write_bytes(render_png())
    except Exception as exc:  # network-dependent (mermaid.ink) — Mermaid source above still works
        print(f"Skipped {PNG_PATH}: {exc}")
    else:
        print(f"Wrote {PNG_PATH}")


if __name__ == "__main__":
    regenerate()
    print(f"Regenerated {DOC_PATH}")

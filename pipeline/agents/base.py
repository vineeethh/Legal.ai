"""Shared machinery for the 6 extraction agents.

Isolation is enforced structurally: an agent's only input is the context text
built from its own routed chunks (see PipelineState.agent_inputs) — nothing
here gives a node access to another agent's output.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from ..chunking import Chunk
from ..llm import get_chat_model

T = TypeVar("T", bound=BaseModel)

ISOLATION_REMINDER = (
    "You only have access to the excerpt below — you do not see the full judgment or "
    "any other agent's output. Each excerpt is preceded by a marker "
    "[[page:P chunk:ID]] recording where it came from.\n\n"
    "Rules:\n"
    "- Every extracted value must carry a verbatim quote copied exactly from the excerpt "
    "it came from, plus the page number and chunk id from that excerpt's marker.\n"
    "- If you cannot confidently find a field in this excerpt, leave it as None/empty — "
    "never guess or infer from outside knowledge.\n"
    "- Do not paraphrase the quote; it must be an exact substring of the excerpt text."
)


def build_context_text(chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"[[page:{c.page} chunk:{c.chunk_id}]]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def run_structured_agent(
    schema: type[T],
    system_prompt: str,
    context_text: str,
    *,
    temperature: float = 0.0,
    model: str | None = None,
) -> T:
    chat = get_chat_model(model=model, temperature=temperature).with_structured_output(schema)
    messages = [
        ("system", f"{system_prompt}\n\n{ISOLATION_REMINDER}"),
        ("human", context_text or "(no routed excerpts for this document)"),
    ]
    result = chat.invoke(messages)
    assert isinstance(result, schema)
    return result

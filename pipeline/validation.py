"""Span-grounded validator — second LLM, no RAG.

Two gates per field, in order:
  1. Deterministic quote-existence check: the SourceRef's `quote` must be an exact
     substring of the chunk it claims to come from. A fabricated/paraphrased quote
     fails here with no LLM call needed — this is a hard, free correctness check.
  2. LLM entailment check: for fields that pass gate 1, a second LLM confirms the
     extracted value is actually entailed by the quote (catches quotes that exist
     verbatim but don't support the claimed value).

Retries are blind: this module has no channel back to the extracting agent beyond
the failed field list used by the retry loop in graph.py — no hints, no reasoning
about *why* it failed are ever passed to the retried agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from schemas import AgentName, AgentValidationResult, FieldValidation, ValidationStatus

from .chunking import Chunk
from .llm import get_chat_model


@dataclass
class SourcedField:
    field_path: str
    value: Any
    sources: list


def walk_sourced_fields(obj: Any, path: str = "") -> list[SourcedField]:
    results: list[SourcedField] = []

    if isinstance(obj, BaseModel):
        if hasattr(obj, "sources") and isinstance(getattr(obj, "sources"), list):
            sources = obj.sources
            if hasattr(obj, "value"):
                value = obj.value
                if value is not None and sources:
                    results.append(SourcedField(path, value, sources))
            else:
                display = getattr(obj, "raw_citation", None)
                if display is not None and sources:
                    results.append(SourcedField(path, display, sources))
            return results

        for name in type(obj).model_fields:
            results.extend(walk_sourced_fields(getattr(obj, name), f"{path}.{name}" if path else name))

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(walk_sourced_fields(item, f"{path}[{i}]"))

    return results


class _ValidationBatch(BaseModel):
    fields: list[FieldValidation] = Field(default_factory=list)


VALIDATOR_SYSTEM_PROMPT = """You are the Validator for an Indian court judgment extraction system.

For each (field_path, extracted_value, supporting_quote) triple below, decide whether
the quote actually entails/supports the extracted value. This is the ONLY thing you
judge — do not use outside knowledge of the case or the law.

Return status "pass" if the quote genuinely supports the value, "fail" otherwise
(e.g. the quote is unrelated, contradicts the value, or is too vague to support it).
Always echo the exact supporting_quote you were given for a "pass" verdict."""


def validate_agent_output(
    agent: AgentName,
    output: BaseModel,
    chunks_by_id: dict[str, Chunk],
    *,
    attempt: int,
) -> AgentValidationResult:
    sourced_fields = walk_sourced_fields(output, "")
    fields: list[FieldValidation] = []
    entailment_candidates: list[SourcedField] = []

    for sf in sourced_fields:
        quote_found = any(
            ref.chunk_id in chunks_by_id and ref.quote in chunks_by_id[ref.chunk_id].text
            for ref in sf.sources
        )
        if not quote_found:
            fields.append(
                FieldValidation(
                    field_path=sf.field_path,
                    status=ValidationStatus.FAIL,
                    supporting_quote=None,
                    reason="Quote not found verbatim in the source chunk it claims to come from.",
                )
            )
        else:
            entailment_candidates.append(sf)

    if entailment_candidates:
        prompt_lines = []
        for sf in entailment_candidates:
            quote = sf.sources[0].quote
            prompt_lines.append(f"field_path: {sf.field_path}\nvalue: {sf.value}\nsupporting_quote: {quote}")
        context = "\n\n---\n\n".join(prompt_lines)

        chat = get_chat_model(temperature=0.0).with_structured_output(_ValidationBatch)
        batch = chat.invoke(
            [("system", VALIDATOR_SYSTEM_PROMPT), ("human", context)]
        )
        assert isinstance(batch, _ValidationBatch)
        fields.extend(batch.fields)

    return AgentValidationResult(agent=agent, attempt=attempt, fields=fields)

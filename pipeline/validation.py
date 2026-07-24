"""Span-grounded validator — second LLM, no RAG.

Two gates per field, in order:
  1. Deterministic quote-existence check: the SourceRef's `quote` must be an exact
     substring of the chunk it claims to come from. A fabricated/paraphrased quote
     fails here with no LLM call needed — this is a hard, free correctness check.
  2. LLM entailment check: for fields that pass gate 1, a second LLM confirms the
     extracted value is actually entailed by the quote (catches quotes that exist
     verbatim but don't support the claimed value).

Two guarantees this module owns:
  - The validator runs on `settings.validator_llm_model`, which can be a *different*
    model from the extractor so the extractor never grades its own homework.
  - Every gate-1-passing field is reconciled to the validator's verdict *by index*.
    A field PASSES only when the validator returned exactly one PASS verdict for it;
    a missing, duplicated, or non-PASS verdict is FAIL. This means a field can never
    silently drop out of the pass-rate denominator (schemas/validation.py) — an
    unanswered field counts against confidence, it does not vanish.

Retries are blind: this module has no channel back to the extracting agent beyond
the failed field list used by the retry loop in graph.py — no hints, no reasoning
about *why* it failed are ever passed to the retried agent.

Import surface is deliberately light (pydantic + schemas only): the LLM/config
imports are lazy, inside `_entailment_check`, so the pure reconciliation logic is
unit-testable without langchain/docling installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from schemas import AgentName, AgentValidationResult, FieldValidation, ValidationStatus

if TYPE_CHECKING:
    from .chunking import Chunk

_WHITESPACE = re.compile(r"\s+")
# Typographic variants an LLM (or OCR) legitimately flattens: curly quotes,
# en/em dashes, non-breaking spaces. Normalizing these does NOT weaken the
# verbatim guarantee — the quote must still reproduce the chunk's characters,
# modulo whitespace runs and quote/dash glyph variants.
_GLYPHS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " "})


def normalize_span(text: str) -> str:
    return _WHITESPACE.sub(" ", text.translate(_GLYPHS)).strip()


def quote_in_chunk(quote: str, chunk_text: str) -> bool:
    """Gate-1 check: exact substring first; if that fails, whitespace/glyph-
    normalized substring. A paraphrase still fails — only layout artifacts
    (line breaks, double spaces, curly vs straight quotes) are forgiven."""
    if quote in chunk_text:
        return True
    return normalize_span(quote) in normalize_span(chunk_text)


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


class _FieldVerdict(BaseModel):
    """One validator verdict, keyed back to the item's `index` in the prompt.

    Kept internal (not schemas.FieldValidation) because the validator only decides
    pass/fail here — field_path and the supporting quote are owned by us, not echoed
    from the model, so the LLM cannot mislabel which field it judged.
    """

    index: int = Field(..., description="Echo of the item's index from the prompt.")
    status: ValidationStatus
    reason: str | None = Field(default=None, description="Why it failed, if it failed.")


class _ValidationBatch(BaseModel):
    verdicts: list[_FieldVerdict] = Field(default_factory=list)


VALIDATOR_SYSTEM_PROMPT = """You are the Validator for an Indian court judgment extraction system.

You are given a numbered list of items, each an (index, field_path, value, supporting_quote)
triple. For each item, decide ONLY whether the supporting_quote actually entails/supports the
extracted value. Do not use any outside knowledge of the case or the law — judge solely whether
the quote supports the value.

Return exactly one verdict per item and echo that item's `index`. Use status "pass" if the quote
genuinely supports the value, "fail" otherwise (the quote is unrelated, contradicts the value, or
is too vague to support it). Return a verdict for every index you were given, and do not invent
indices that were not in the list."""


def _reconcile(
    candidates: list[tuple[SourcedField, str]], batch: _ValidationBatch
) -> list[FieldValidation]:
    """Map the validator's index-keyed verdicts back onto the candidates.

    A candidate PASSES only if the batch contains exactly one verdict for its index
    with status PASS. No verdict, multiple verdicts, or any non-PASS status all
    resolve to FAIL — so the returned list always has one entry per candidate and a
    field can never silently disappear from scoring."""
    verdicts_by_index: dict[int, list[_FieldVerdict]] = {}
    for verdict in batch.verdicts:
        verdicts_by_index.setdefault(verdict.index, []).append(verdict)

    results: list[FieldValidation] = []
    for i, (sf, quote) in enumerate(candidates):
        matched = verdicts_by_index.get(i, [])
        if len(matched) == 1 and matched[0].status == ValidationStatus.PASS:
            results.append(
                FieldValidation(
                    field_path=sf.field_path,
                    status=ValidationStatus.PASS,
                    supporting_quote=quote,
                    reason=None,
                )
            )
        elif len(matched) == 1 and matched[0].status == ValidationStatus.FAIL:
            results.append(
                FieldValidation(
                    field_path=sf.field_path,
                    status=ValidationStatus.FAIL,
                    supporting_quote=None,
                    reason=matched[0].reason or "Validator judged the quote does not support the value.",
                )
            )
        else:
            reason = (
                "Validator returned no verdict for this field."
                if not matched
                else "Validator returned an ambiguous or duplicate verdict for this field."
            )
            results.append(
                FieldValidation(
                    field_path=sf.field_path,
                    status=ValidationStatus.FAIL,
                    supporting_quote=None,
                    reason=reason,
                )
            )
    return results


def _fail_all(candidates: list[tuple[SourcedField, str]], reason: str) -> list[FieldValidation]:
    return [
        FieldValidation(field_path=sf.field_path, status=ValidationStatus.FAIL, supporting_quote=None, reason=reason)
        for sf, _quote in candidates
    ]


def _entailment_check(candidates: list[tuple[SourcedField, str]]) -> list[FieldValidation]:
    """Run the second-LLM entailment gate over gate-1-passing candidates.

    Imports the LLM/config lazily so this module stays importable (and its pure
    reconciliation testable) without the heavy runtime deps.

    This runs inside the graph's confidence node, not an extraction agent node —
    it is NOT covered by pipeline/graph.py's per-agent error isolation. A weak
    or unavailable validator model must never crash the whole document run, so
    any failure here (bad structured output, a network error, anything) FAILS
    every candidate rather than raising. That is the safe default: if the
    validator itself can't be trusted to judge a field, the field does not pass
    — consistent with 'None over guessing' applied to the validator itself.
    """
    from .config import get_settings
    from .llm import get_chat_model

    prompt_lines = [
        f"index: {i}\nfield_path: {sf.field_path}\nvalue: {sf.value}\nsupporting_quote: {quote}"
        for i, (sf, quote) in enumerate(candidates)
    ]
    context = "\n\n---\n\n".join(prompt_lines)

    settings = get_settings()
    try:
        # Validator verdicts are tiny; cap the budget so this call can't request
        # the model's max ceiling (see llm_config.py's max_tokens note).
        # method="function_calling" for the same cross-model robustness as the
        # extraction agents (see pipeline/agents/base.py).
        chat = get_chat_model(
            model=settings.validator_llm_model, temperature=0.0, max_tokens=4096
        ).with_structured_output(_ValidationBatch, method="function_calling")
        batch = chat.invoke([("system", VALIDATOR_SYSTEM_PROMPT), ("human", context)])
        if not isinstance(batch, _ValidationBatch):
            return _fail_all(candidates, "Validator returned no valid structured output.")
    except Exception as exc:
        return _fail_all(candidates, f"Validator call failed ({type(exc).__name__}).")

    return _reconcile(candidates, batch)


def validate_agent_output(
    agent: AgentName,
    output: BaseModel,
    chunks_by_id: dict[str, "Chunk"],
    *,
    attempt: int,
) -> AgentValidationResult:
    sourced_fields = walk_sourced_fields(output, "")
    fields: list[FieldValidation] = []
    # Each candidate carries the exact quote that was found verbatim in its chunk,
    # so the entailment gate judges the same span gate 1 verified (not blindly
    # sources[0], which may not be the one that matched).
    candidates: list[tuple[SourcedField, str]] = []

    for sf in sourced_fields:
        verified_quote = next(
            (
                ref.quote
                for ref in sf.sources
                if ref.chunk_id in chunks_by_id and quote_in_chunk(ref.quote, chunks_by_id[ref.chunk_id].text)
            ),
            None,
        )
        if verified_quote is None:
            fields.append(
                FieldValidation(
                    field_path=sf.field_path,
                    status=ValidationStatus.FAIL,
                    supporting_quote=None,
                    reason="Quote not found verbatim in the source chunk it claims to come from.",
                )
            )
        else:
            candidates.append((sf, verified_quote))

    if candidates:
        fields.extend(_entailment_check(candidates))

    return AgentValidationResult(agent=agent, attempt=attempt, fields=fields)

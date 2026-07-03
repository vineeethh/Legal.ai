"""Wires the Statute Agent's raw output to statute_kb.lookup — the only place
this pipeline touches the KB. Runs after the Statute Agent, before validation."""

from __future__ import annotations

from datetime import date

from schemas import StatuteOutput

from statute_kb.lookup import verify_citation


def verify_statute_output(statute_output: StatuteOutput, *, as_of_date: date | None = None) -> StatuteOutput:
    verified_refs = []
    for ref in statute_output.references:
        quoted_text = ref.sources[0].quote if ref.sources else None
        result = verify_citation(
            parsed_act=ref.parsed_act,
            parsed_section=ref.parsed_section,
            quoted_text=quoted_text,
            as_of_date=as_of_date,
        )
        verified_refs.append(
            ref.model_copy(
                update={
                    "verification_status": result.status,
                    "kb_match": result.kb_match,
                    "verification_note": result.note,
                    "current_equivalent": result.current_equivalent,
                }
            )
        )
    return statute_output.model_copy(update={"references": verified_refs})

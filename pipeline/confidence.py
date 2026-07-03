"""Deterministic confidence scoring — no LLM. Computes the 5 signals in
schemas/confidence.py from the final PipelineState and applies the fixed
score->decision thresholds.
"""

from __future__ import annotations

from schemas import (
    AgentName,
    ArgumentsOutput,
    ConfidenceBreakdown,
    ConfidenceWeights,
    EvidenceOutput,
    FactsOutput,
    MetadataOutput,
    StatuteOutput,
)

from .validation import walk_sourced_fields

EXTRACTION_AGENTS = [
    AgentName.METADATA,
    AgentName.FACTS,
    AgentName.STATUTE,
    AgentName.PETITIONER,
    AgentName.RESPONDENT,
    AgentName.EVIDENCE,
]

# Field paths checked for schema_completeness — a fixed notion of "the core
# fields a usable judgment record should have", independent of any one document.
EXPECTED_FIELD_CHECKS = [
    ("metadata.court", lambda m: m.court.is_present),
    ("metadata.decision_date", lambda m: m.decision_date.is_present),
    ("metadata.case_number", lambda m: m.case_number.is_present),
]


def _validation_pass_rate(validations: dict) -> float:
    rates = [v.pass_rate for agent, v in validations.items() if agent in EXTRACTION_AGENTS]
    return sum(rates) / len(rates) if rates else 1.0


def _provenance_coverage(
    metadata: MetadataOutput,
    facts: FactsOutput,
    statutes: StatuteOutput,
    petitioner: ArgumentsOutput,
    respondent: ArgumentsOutput,
    evidence: EvidenceOutput,
) -> float:
    """Fraction of extracted (present) fields whose SourceRef carries enough
    metadata (chunk_id + page) to be traced back to the document — distinct
    from validation_pass_rate, which judges whether the quote *entails* the
    value rather than whether provenance metadata is populated."""
    sourced_fields = []
    for output in (metadata, facts, statutes, petitioner, respondent, evidence):
        sourced_fields.extend(walk_sourced_fields(output))

    if not sourced_fields:
        return 1.0

    traceable = sum(
        1
        for sf in sourced_fields
        if any(ref.chunk_id is not None and ref.page is not None for ref in sf.sources)
    )
    return traceable / len(sourced_fields)


def _schema_completeness(metadata: MetadataOutput) -> float:
    checks = [check(metadata) for _, check in EXPECTED_FIELD_CHECKS]
    return sum(checks) / len(checks) if checks else 1.0


def _cross_agent_consistency(metadata: MetadataOutput, facts: FactsOutput) -> float:
    """Minimal, extensible: currently checks that no timeline event postdates
    the judgment's decision date. Defaults to 1.0 (no penalty) when either
    side of the check is missing — this only penalizes a detected
    contradiction, never an absence of data (that's schema_completeness's job)."""
    if not metadata.decision_date.is_present or not facts.timeline:
        return 1.0

    decision_date = metadata.decision_date.value
    violations = sum(
        1
        for item in facts.timeline
        if item.value.event_date is not None and item.value.event_date > decision_date
    )
    return 1.0 if violations == 0 else max(0.0, 1.0 - violations / len(facts.timeline))


def compute_confidence(
    *,
    metadata: MetadataOutput,
    facts: FactsOutput,
    statutes: StatuteOutput,
    petitioner: ArgumentsOutput,
    respondent: ArgumentsOutput,
    evidence: EvidenceOutput,
    validations: dict,
    weights: ConfidenceWeights | None = None,
) -> ConfidenceBreakdown:
    weights = weights or ConfidenceWeights()

    signals = {
        "validation_pass_rate": _validation_pass_rate(validations),
        "statute_verification_rate": statutes.verification_rate,
        "provenance_coverage": _provenance_coverage(
            metadata, facts, statutes, petitioner, respondent, evidence
        ),
        "schema_completeness": _schema_completeness(metadata),
        "cross_agent_consistency": _cross_agent_consistency(metadata, facts),
    }

    score = (
        signals["validation_pass_rate"] * weights.validation_pass_rate
        + signals["statute_verification_rate"] * weights.statute_verification_rate
        + signals["provenance_coverage"] * weights.provenance_coverage
        + signals["schema_completeness"] * weights.schema_completeness
        + signals["cross_agent_consistency"] * weights.cross_agent_consistency
    )

    return ConfidenceBreakdown(**signals, score=score, decision=ConfidenceBreakdown.decide(score))

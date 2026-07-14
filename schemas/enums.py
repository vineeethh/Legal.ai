"""Shared enumerations for the Legal AI extraction pipeline.

Kept in one module so every schema, validator, and the confidence engine agree on
the exact set of legal states. Values are lowercase strings for stable JSON/DB storage.
"""

from __future__ import annotations

from enum import Enum


class AgentName(str, Enum):
    """The seven agents. Six extract; the response agent only assembles."""

    METADATA = "metadata"
    FACTS = "facts"
    STATUTE = "statute"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    EVIDENCE = "evidence"
    RESPONSE = "response"


class ValidationStatus(str, Enum):
    """Result of the second-LLM, span-grounded validation for a field or agent."""

    PASS = "pass"
    FAIL = "fail"
    # Field was intentionally None (nothing to validate) — not a failure.
    NOT_APPLICABLE = "not_applicable"


class StatuteAct(str, Enum):
    """Acts present in the Qdrant + Postgres knowledge base.

    Old and new acts coexist indefinitely — pre-2024 offenses are tried under
    the law in force at the time of the offense (Article 20(1)), so IPC/CrPC/
    Evidence Act citations remain legitimate for decades after BNS/BNSS/BSA
    took effect. Never remove an act here; see data/README.md.
    """

    IPC = "indian_penal_code"
    CRPC = "code_of_criminal_procedure"
    EVIDENCE_ACT = "indian_evidence_act"
    CONSTITUTION = "constitution_of_india"
    BNS = "bharatiya_nyaya_sanhita"
    BNSS = "bharatiya_nagarik_suraksha_sanhita"
    BSA = "bharatiya_sakshya_adhiniyam"
    # Sentinel for citations the extractor found but that map to no KB act.
    UNKNOWN = "unknown"


class ActFamily(str, Enum):
    """Groups an old act with its replacement for crosswalk lookups."""

    CRIMINAL_SUBSTANTIVE = "criminal_substantive"  # IPC <-> BNS
    CRIMINAL_PROCEDURAL = "criminal_procedural"    # CrPC <-> BNSS
    EVIDENCE = "evidence"                          # Evidence Act <-> BSA
    CONSTITUTIONAL = "constitutional"              # Constitution (no successor)


ACT_FAMILY: dict[StatuteAct, ActFamily] = {
    StatuteAct.IPC: ActFamily.CRIMINAL_SUBSTANTIVE,
    StatuteAct.BNS: ActFamily.CRIMINAL_SUBSTANTIVE,
    StatuteAct.CRPC: ActFamily.CRIMINAL_PROCEDURAL,
    StatuteAct.BNSS: ActFamily.CRIMINAL_PROCEDURAL,
    StatuteAct.EVIDENCE_ACT: ActFamily.EVIDENCE,
    StatuteAct.BSA: ActFamily.EVIDENCE,
    StatuteAct.CONSTITUTION: ActFamily.CONSTITUTIONAL,
}


class VerificationStatus(str, Enum):
    """Outcome of cross-referencing an extracted citation against the KB."""

    # Citation found in KB and the section text matches.
    VERIFIED = "verified"
    # Citation's act/section not present in the KB at all.
    NOT_FOUND = "not_found"
    # Section number exists but under a different act, or text disagrees.
    MISMATCH = "mismatch"
    # Verification not attempted (e.g., citation could not be parsed).
    SKIPPED = "skipped"


class ReviewDecision(str, Enum):
    """Deterministic routing decision derived from the confidence score."""

    AUTO_SAVE = "auto_save"          # score >= 0.90
    NEEDS_REVIEW = "needs_review"    # 0.80 <= score < 0.90
    HUMAN_REQUIRED = "human_required"  # score < 0.80


class EvidenceKind(str, Enum):
    WITNESS = "witness"
    DOCUMENT = "document"
    PHYSICAL = "physical"
    DIGITAL = "digital"

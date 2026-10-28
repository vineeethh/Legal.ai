"""Demo pipeline — a scripted stand-in for the real one, for machines that can't
run Docling/torch or have no LLM credentials.

It walks through the same graph node names as pipeline/graph.py (so the UI's
progress view behaves the same), then returns a SYNTHETIC StructuredJudgment
built through the real Pydantic schemas. The case below is fictional; no LLM,
OCR or database is involved. Every result says so in processing.llm_model.

Filename triggers (case-insensitive), so every path can be shown in a demo:
  - contains "unsafe" -> rejected by the safety gate
  - contains "review" -> low confidence, pauses for human review
  - anything else     -> high confidence, auto-saved
"""

from __future__ import annotations

import time
from typing import Any

from schemas import ReviewDecision, StructuredJudgment
from schemas.confidence import ConfidenceBreakdown, ConfidenceWeights

from .jobs import EXTRACTION_AGENTS, Job
from .pipelines import DocumentRejected, PipelineOutcome, ProgressFn, ReviewFn

DEMO_MODEL_LABEL = "demo-mode (synthetic result, no LLM call)"


def _src(page: int, quote: str, section: str, chunk: int) -> dict:
    return {
        "page": page,
        "quote": quote,
        "chunk_id": f"demo-chunk-{chunk:02d}",
        "section_path": section,
    }


def _sourced(value: Any, *sources: dict) -> dict:
    return {"value": value, "sources": list(sources)}


HEADER = "IN THE HIGH COURT OF KARNATAKA AT BENGALURU"
FACTS = "JUDGMENT > BRIEF FACTS"
SUBMISSIONS_A = "JUDGMENT > SUBMISSIONS OF THE APPELLANT"
SUBMISSIONS_R = "JUDGMENT > SUBMISSIONS OF THE RESPONDENT"
EVIDENCE = "JUDGMENT > EVIDENCE ON RECORD"
ANALYSIS = "JUDGMENT > ANALYSIS"

IPC_302_TEXT = (
    "302. Punishment for murder.—Whoever commits murder shall be punished with death, "
    "or imprisonment for life, and shall also be liable to fine."
)
IPC_34_TEXT = (
    "34. Acts done by several persons in furtherance of common intention.—When a criminal "
    "act is done by several persons in furtherance of the common intention of all, each of "
    "such persons is liable for that act in the same manner as if it were done by him alone."
)
CRPC_313_TEXT = (
    "313. Power to examine the accused.—(1) In every inquiry or trial, for the purpose of "
    "enabling the accused personally to explain any circumstances appearing in the evidence "
    "against him, the Court ..."
)
BNS_103_TEXT = (
    "103. Punishment for murder.—(1) Whoever commits murder shall be punished with death or "
    "imprisonment for life, and shall also be liable to fine."
)


def _kb(act: str, version: str, section: str, title: str, text: str, score: float) -> dict:
    return {
        "act": act,
        "act_version": version,
        "section_number": section,
        "section_title": title,
        "official_text": text,
        "similarity_score": score,
    }


def _signals(low_confidence: bool) -> dict[str, float]:
    if low_confidence:
        return {
            "validation_pass_rate": 0.62,
            "statute_verification_rate": 0.5,
            "provenance_coverage": 0.9,
            "schema_completeness": 2 / 3,
            "cross_agent_consistency": 1.0,
        }
    return {
        "validation_pass_rate": 0.9,
        "statute_verification_rate": 0.75,
        "provenance_coverage": 1.0,
        "schema_completeness": 1.0,
        "cross_agent_consistency": 1.0,
    }


def _confidence(low_confidence: bool) -> ConfidenceBreakdown:
    """Same weighted sum as pipeline/confidence.py, applied to fixed demo signals."""
    signals = _signals(low_confidence)
    weights = ConfidenceWeights()
    score = sum(value * getattr(weights, name) for name, value in signals.items())
    return ConfidenceBreakdown(**signals, score=score, decision=ConfidenceBreakdown.decide(score))


def build_demo_judgment(document_id: str, *, low_confidence: bool = False) -> StructuredJudgment:
    confidence = _confidence(low_confidence)

    metadata = {
        "court": _sourced("High Court of Karnataka at Bengaluru", _src(1, HEADER, "root", 1)),
        "bench": _sourced(
            "Division Bench",
            _src(1, "BEFORE THE DIVISION BENCH", "root", 1),
        ),
        "judges": [
            {"value": "Justice A. R. Menon", "sources": [_src(1, "HON'BLE MR. JUSTICE A. R. MENON", "root", 1)]},
            {"value": "Justice S. K. Rao", "sources": [_src(1, "HON'BLE MRS. JUSTICE S. K. RAO", "root", 1)]},
        ],
        "decision_date": _sourced("2021-03-15", _src(1, "DATED THIS THE 15TH DAY OF MARCH, 2021", "root", 1)),
        "case_number": _sourced(
            "Criminal Appeal No. 412 of 2018",
            _src(1, "CRIMINAL APPEAL No. 412 OF 2018", "root", 2),
        ),
        "petitioners": [
            {
                "value": {"name": "Ramesh Kumar", "role": "Appellant"},
                "sources": [_src(1, "Ramesh Kumar, aged about 34 years ... APPELLANT", "root", 2)],
            }
        ],
        "respondents": [
            {
                "value": {"name": "State of Karnataka", "role": "Respondent"},
                "sources": [_src(1, "State of Karnataka, by Hebbal Police Station ... RESPONDENT", "root", 2)],
            }
        ],
        "jurisdiction": _sourced(
            "Criminal appellate jurisdiction under Section 374(2) CrPC",
            _src(2, "This appeal is filed under Section 374(2) of Cr.P.C.", "JUDGMENT", 3),
        ),
    }
    if low_confidence:
        # Case number never validated after retries -> pruned to None ("None over guessing").
        metadata["case_number"] = {"value": None, "sources": []}

    facts = {
        "background": _sourced(
            "The appellant and the deceased were neighbours with a long-running dispute over a boundary wall.",
            _src(
                2,
                "the appellant and the deceased were neighbours and there was a long-standing dispute "
                "between them regarding the boundary wall",
                FACTS,
                4,
            ),
        ),
        "incident_summary": _sourced(
            "On the night of 12 August 2016 the deceased was assaulted with a knife near his house and died of his injuries.",
            _src(
                2,
                "on 12.08.2016 at about 10.30 p.m. the accused assaulted the deceased with a knife near "
                "his house",
                FACTS,
                4,
            ),
        ),
        "key_facts": [
            {
                "value": "PW-1, the deceased's brother, claims to have witnessed the assault.",
                "sources": [_src(3, "PW-1, the brother of the deceased, has deposed that he witnessed the incident", FACTS, 5)],
            },
            {
                "value": "The knife (MO-1) was recovered at the appellant's instance.",
                "sources": [_src(3, "MO-1 knife was recovered at the instance of the accused", FACTS, 5)],
            },
            {
                "value": "The trial court convicted the appellant under Section 302 read with Section 34 IPC.",
                "sources": [
                    _src(3, "convicted the accused for the offence punishable under Section 302 r/w 34 of IPC", FACTS, 6)
                ],
            },
        ],
        "timeline": [
            {
                "value": {"event_date": "2016-08-12", "description": "Assault on the deceased near his house."},
                "sources": [_src(2, "on 12.08.2016 at about 10.30 p.m.", FACTS, 4)],
            },
            {
                "value": {"event_date": "2016-08-13", "description": "FIR registered at Hebbal Police Station."},
                "sources": [_src(2, "FIR came to be registered on 13.08.2016", FACTS, 4)],
            },
            {
                "value": {"event_date": "2018-01-20", "description": "Trial court judgment convicting the appellant."},
                "sources": [_src(3, "judgment dated 20.01.2018 passed by the learned Sessions Judge", FACTS, 6)],
            },
        ],
    }

    statutes = {
        "references": [
            {
                "raw_citation": "Section 302 IPC",
                "parsed_act": "indian_penal_code",
                "parsed_section": "302",
                "sources": [_src(3, "offence punishable under Section 302 r/w 34 of IPC", FACTS, 6)],
                "verification_status": "verified",
                "kb_match": _kb("indian_penal_code", "IPC-1860", "302", "Punishment for murder", IPC_302_TEXT, 0.91),
                "current_equivalent": _kb(
                    "bharatiya_nyaya_sanhita", "BNS-2023", "103", "Punishment for murder", BNS_103_TEXT, 1.0
                ),
            },
            {
                "raw_citation": "Section 34 IPC",
                "parsed_act": "indian_penal_code",
                "parsed_section": "34",
                "sources": [_src(3, "offence punishable under Section 302 r/w 34 of IPC", FACTS, 6)],
                "verification_status": "verified",
                "kb_match": _kb(
                    "indian_penal_code",
                    "IPC-1860",
                    "34",
                    "Acts done by several persons in furtherance of common intention",
                    IPC_34_TEXT,
                    0.87,
                ),
            },
            {
                "raw_citation": "Section 313 Cr.P.C.",
                "parsed_act": "code_of_criminal_procedure",
                "parsed_section": "313",
                "sources": [_src(5, "the statement of the accused under Section 313 of Cr.P.C.", ANALYSIS, 11)],
                "verification_status": "verified",
                "kb_match": _kb(
                    "code_of_criminal_procedure",
                    "CrPC-1973",
                    "313",
                    "Power to examine the accused",
                    CRPC_313_TEXT,
                    0.78,
                ),
            },
            {
                "raw_citation": "Article 21 of the Constitution",
                "parsed_act": "constitution_of_india",
                "parsed_section": "21",
                "sources": [_src(6, "the right guaranteed under Article 21 of the Constitution", ANALYSIS, 13)],
                "verification_status": "not_found",
                "verification_note": "No KB entry for constitution_of_india section 21.",
            },
        ]
    }
    if low_confidence:
        statutes["references"][2]["verification_status"] = "mismatch"
        statutes["references"][2]["verification_note"] = (
            "Quoted text diverges from canonical section text (similarity=0.41)."
        )

    petitioner = {
        "party_side": "petitioner",
        "arguments": [
            {
                "value": {
                    "summary": "PW-1 is an interested witness and his testimony is not corroborated by independent witnesses.",
                    "relied_on": None,
                },
                "sources": [_src(4, "PW-1 being an interested witness, his evidence requires corroboration", SUBMISSIONS_A, 7)],
            },
            {
                "value": {
                    "summary": "The recovery of MO-1 was not proved, as the panch witness turned hostile.",
                    "relied_on": "Section 27 of the Indian Evidence Act",
                },
                "sources": [_src(4, "the panch witness to the recovery has turned hostile", SUBMISSIONS_A, 7)],
            },
        ],
    }
    respondent = {
        "party_side": "respondent",
        "arguments": [
            {
                "value": {
                    "summary": "The evidence of a related witness cannot be discarded only because of the relationship.",
                    "relied_on": None,
                },
                "sources": [
                    _src(4, "evidence of a related witness cannot be discarded merely on the ground of relationship", SUBMISSIONS_R, 8)
                ],
            },
            {
                "value": {
                    "summary": "The medical evidence (Ext. P-5) is consistent with the eyewitness account.",
                    "relied_on": None,
                },
                "sources": [_src(4, "the medical evidence fully corroborates the ocular testimony", SUBMISSIONS_R, 8)],
            },
        ],
    }
    evidence = {
        "items": [
            {
                "value": {"kind": "witness", "description": "Brother of the deceased; eyewitness to the assault.", "label": "PW-1"},
                "sources": [_src(3, "PW-1, the brother of the deceased", EVIDENCE, 9)],
            },
            {
                "value": {"kind": "witness", "description": "Doctor who conducted the post-mortem.", "label": "PW-6"},
                "sources": [_src(5, "PW-6 the doctor who conducted the post-mortem examination", EVIDENCE, 10)],
            },
            {
                "value": {"kind": "document", "description": "Post-mortem report.", "label": "Ext. P-5"},
                "sources": [_src(5, "post-mortem report as per Ex.P-5", EVIDENCE, 10)],
            },
            {
                "value": {"kind": "physical", "description": "Knife recovered at the appellant's instance.", "label": "MO-1"},
                "sources": [_src(3, "MO-1 knife was recovered at the instance of the accused", EVIDENCE, 9)],
            },
            {
                "value": {"kind": "digital", "description": "CCTV footage from a nearby shop.", "label": None},
                "sources": [_src(5, "CCTV footage collected from the shop near the spot", EVIDENCE, 10)],
            },
        ]
    }

    retry_counts = {"statute": 1, "facts": 2} if low_confidence else {"statute": 1}
    return StructuredJudgment.model_validate(
        {
            "metadata": metadata,
            "facts": facts,
            "statutes": statutes,
            "petitioner": petitioner,
            "respondent": respondent,
            "evidence": evidence,
            "confidence": confidence.model_dump(),
            "review_decision": confidence.decision,
            "processing": {
                "document_id": document_id,
                "llm_model": DEMO_MODEL_LABEL,
                "retry_counts": retry_counts,
            },
        }
    )


def build_review_payload(document_id: str, judgment: StructuredJudgment) -> dict:
    """Same shape as the interrupt payload built by human_review_node in pipeline/graph.py."""
    return {
        "document_id": document_id,
        "decision": judgment.confidence.decision.value,
        "confidence_score": judgment.confidence.score,
        "flagged_fields": [
            {
                "agent": "metadata",
                "field_path": "case_number",
                "status": "fail",
                "reason": "Quote not found verbatim in the source chunk it claims to come from.",
            },
            {
                "agent": "facts",
                "field_path": "key_facts[1]",
                "status": "fail",
                "reason": "The quote does not state who the recovery was made from.",
            },
            {
                "agent": "statute",
                "field_path": "references[2]",
                "status": "fail",
                "reason": "Quoted text diverges from canonical section text.",
            },
        ],
        "result_preview": judgment.model_dump(mode="json"),
    }


def apply_review_decision(judgment: StructuredJudgment, decision: dict) -> StructuredJudgment:
    """Mirrors human_review_node in pipeline/graph.py."""
    action = decision.get("action")
    if action == "reject":
        return judgment.model_copy(update={"review_decision": ReviewDecision.HUMAN_REQUIRED})
    if action == "edit":
        patched = judgment.model_dump(mode="json")
        patched.update(decision.get("patches") or {})
        return StructuredJudgment.model_validate(patched)
    return judgment


class DemoPipeline:
    def __init__(self, *, step_seconds: float):
        self.step_seconds = step_seconds

    def check_ready(self) -> None:
        return None

    def run(self, job: Job, on_progress: ProgressFn, on_review: ReviewFn) -> PipelineOutcome:
        name = job.filename.lower()
        low_confidence = "review" in name

        def emit(node: str, update: dict | None = None, *, pause: float | None = None) -> None:
            time.sleep(self.step_seconds if pause is None else pause)
            on_progress(node, update or {})

        emit("pdf_safety_gate", {"pdf_safety_reasons": []})
        if "unsafe" in name:
            raise DocumentRejected(
                ["has_embedded_javascript", "has_open_action (demo mode: triggered by the filename)"]
            )
        emit("parse_and_chunk", {"chunk_count": 42, "ocr_used": False})
        emit("injection_screen", {"injection_matches": {}})

        retry_once = {"statute", "facts"} if low_confidence else {"statute"}
        for agent in EXTRACTION_AGENTS:
            emit(agent, pause=self.step_seconds / 3)
        for agent in EXTRACTION_AGENTS:
            will_retry = agent in retry_once
            emit(
                f"{agent}_confidence",
                {
                    "retry_decision": {agent: "retry" if will_retry else "done"},
                    "retry_counts": {agent: 1 if will_retry else 0},
                },
                pause=self.step_seconds / 2,
            )
        for agent in EXTRACTION_AGENTS:
            if agent in retry_once:
                emit(agent)
                emit(f"{agent}_confidence", {"retry_decision": {agent: "done"}, "retry_counts": {agent: 1}})

        emit("fan_in_gate")
        emit("assemble")
        judgment = build_demo_judgment(job.id, low_confidence=low_confidence)
        emit("confidence")

        decision = None
        if judgment.review_decision == ReviewDecision.HUMAN_REQUIRED:
            decision = on_review(build_review_payload(job.id, judgment))
            judgment = apply_review_decision(judgment, decision)
            emit("human_review", pause=0)

        return PipelineOutcome(
            result=judgment.model_dump(mode="json"),
            human_review_decision=decision,
            processing_run_id=None,
        )

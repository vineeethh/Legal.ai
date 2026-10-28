"""Scoring: compare one pipeline output (StructuredJudgment) with one gold label.

Scalar fields get one of five outcomes:

    gold has value, prediction matches      -> correct
    gold has value, prediction is None      -> missed     (abstained)
    gold has value, prediction differs      -> wrong
    gold is null,   prediction is None      -> correct_absent
    gold is null,   prediction has a value  -> spurious   (invented)

Splitting "missed" from "wrong"/"spurious" is the point: the pipeline is built
to return None rather than guess, so the interesting numbers are how often it
is wrong *when it answers* versus how often it declines to answer.

List fields (judges, parties, statutes, evidence labels, timeline dates) are
scored with precision / recall / F1 after one-to-one matching.

Matching is deliberately forgiving about formatting ("Hon'ble Mr. Justice A. R.
Menon" == "A R Menon"; "Crl.A. 412/2018" == "Criminal Appeal No. 412 of 2018")
and strict about content. All matching rules live in this file.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel

from schemas import StructuredJudgment

from .gold import LIST_FIELDS, SCALAR_FIELDS, GoldJudgment

FUZZY_THRESHOLD = 0.85

# Dropped before comparing person names. "j" covers the trailing ", J." in
# Indian judgments ("A. R. Menon, J.").
HONORIFICS = {"hon", "ble", "honble", "honourable", "justice", "mr", "mrs", "ms", "dr", "shri", "smt", "sri", "j", "cj"}


# --------------------------------------------------------------------------- normalisation


def normalize_text(value: Any) -> str:
    """Lowercase, punctuation -> space, collapse whitespace."""
    text = str(value).lower().replace("'", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_person(value: Any) -> str:
    return " ".join(t for t in normalize_text(value).split() if t not in HONORIFICS)


def normalize_section(value: Any) -> str:
    """'Section 304-B' / '304 B' / 's. 304b' -> '304b'."""
    text = normalize_text(value)
    text = re.sub(r"^(section|sec|s|article|art)\s+", "", text)
    return text.replace(" ", "")


def normalize_label(value: Any) -> str:
    """'Ext. P-5' / 'Ex.P5' / 'Exhibit P 5' -> 'exp5';  'PW-1' -> 'pw1'."""
    text = normalize_text(value).replace(" ", "")
    return re.sub(r"^(exhibit|exh|ext|ex)", "ex", text)


def _digit_groups(value: Any) -> list[str]:
    return [g.lstrip("0") or "0" for g in re.findall(r"\d+", str(value))]


# --------------------------------------------------------------------------- matchers


def text_match(gold: Any, pred: Any, *, normalize: Callable[[Any], str] = normalize_text) -> bool:
    g, p = normalize(gold), normalize(pred)
    if not g or not p:
        return False
    if g == p or SequenceMatcher(None, g, p).ratio() >= FUZZY_THRESHOLD:
        return True
    # One side is a more complete version of the other:
    # "High Court of Karnataka" vs "High Court of Karnataka at Bengaluru".
    g_tokens, p_tokens = set(g.split()), set(p.split())
    smaller, larger = sorted((g_tokens, p_tokens), key=len)
    return len(smaller) >= 2 and smaller <= larger


def person_match(gold: Any, pred: Any) -> bool:
    return text_match(gold, pred, normalize=normalize_person)


def case_number_match(gold: Any, pred: Any) -> bool:
    """Same text, or the same sequence of numbers (412, 2018) however it's written."""
    if text_match(gold, pred):
        return True
    g, p = _digit_groups(gold), _digit_groups(pred)
    return bool(g) and g == p


def exact_match(gold: Any, pred: Any) -> bool:
    return gold == pred


SCALAR_MATCHERS: dict[str, Callable[[Any, Any], bool]] = {
    "court": text_match,
    "bench": text_match,
    "decision_date": exact_match,
    "case_number": case_number_match,
    "jurisdiction": text_match,
}


# --------------------------------------------------------------------------- outcomes


class Outcome(str, Enum):
    CORRECT = "correct"
    CORRECT_ABSENT = "correct_absent"
    MISSED = "missed"
    WRONG = "wrong"
    SPURIOUS = "spurious"


def score_scalar(gold: Any, pred: Any, matcher: Callable[[Any, Any], bool]) -> Outcome:
    if gold is None:
        return Outcome.CORRECT_ABSENT if pred is None else Outcome.SPURIOUS
    if pred is None:
        return Outcome.MISSED
    return Outcome.CORRECT if matcher(gold, pred) else Outcome.WRONG


@dataclass
class ListScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        if self.tp + self.fp + self.fn == 0:
            return 1.0  # nothing to find and nothing claimed
        p, r = self.precision or 0.0, self.recall or 0.0
        return 2 * p * r / (p + r) if p + r else 0.0

    def __iadd__(self, other: "ListScore") -> "ListScore":
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        return self

    def to_dict(self) -> dict:
        return {**asdict(self), "precision": self.precision, "recall": self.recall, "f1": self.f1}


def score_list(gold: list, pred: list, matcher: Callable[[Any, Any], bool]) -> ListScore:
    """One-to-one greedy matching: each gold item can be claimed by at most one prediction."""
    remaining = list(pred)
    tp = 0
    for g in gold:
        for i, p in enumerate(remaining):
            if matcher(g, p):
                tp += 1
                del remaining[i]
                break
    return ListScore(tp=tp, fp=len(remaining), fn=len(gold) - tp)


def _statute_match(gold: tuple, pred: tuple) -> bool:
    return gold[0] == pred[0] and normalize_section(gold[1]) == normalize_section(pred[1])


def _label_match(gold: Any, pred: Any) -> bool:
    return normalize_label(gold) == normalize_label(pred)


LIST_MATCHERS: dict[str, Callable[[Any, Any], bool]] = {
    "judges": person_match,
    "petitioners": person_match,
    "respondents": person_match,
    "statutes": _statute_match,
    "evidence_labels": _label_match,
    "timeline_dates": exact_match,
}


# --------------------------------------------------------------------------- extraction


def predicted_scalars(pred: StructuredJudgment) -> dict[str, Any]:
    md = pred.metadata
    return {name: getattr(md, name).value for name in SCALAR_FIELDS}


def predicted_lists(pred: StructuredJudgment) -> dict[str, list]:
    md = pred.metadata
    return {
        "judges": [item.value for item in md.judges],
        "petitioners": [item.value.name for item in md.petitioners],
        "respondents": [item.value.name for item in md.respondents],
        "statutes": [
            (ref.parsed_act.value, ref.parsed_section) for ref in pred.statutes.references if ref.parsed_section
        ],
        "evidence_labels": [item.value.label for item in pred.evidence.items if item.value.label],
        "timeline_dates": [item.value.event_date for item in pred.facts.timeline if item.value.event_date],
    }


def gold_lists(gold: GoldJudgment) -> dict[str, list]:
    md = gold.metadata
    return {
        "judges": md.judges,
        "petitioners": md.petitioners,
        "respondents": md.respondents,
        "statutes": [(s.act.value, s.section) for s in gold.statutes],
        "evidence_labels": gold.evidence_labels,
        "timeline_dates": gold.timeline_dates,
    }


# --------------------------------------------------------------------------- per document


@dataclass
class DocumentScore:
    case_id: str
    confidence_score: float
    review_decision: str
    scalars: dict[str, Outcome] = field(default_factory=dict)
    lists: dict[str, ListScore] = field(default_factory=dict)
    statute_verification: dict[str, int] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    sourced_values: int = 0
    sourced_values_with_chunk: int = 0

    @property
    def scalar_accuracy(self) -> float | None:
        if not self.scalars:
            return None
        good = sum(o in (Outcome.CORRECT, Outcome.CORRECT_ABSENT) for o in self.scalars.values())
        return good / len(self.scalars)

    @property
    def doc_score(self) -> float | None:
        """One number per document, for checking confidence calibration:
        mean of scalar accuracy and the mean F1 of the labelled list fields."""
        parts = []
        if self.scalar_accuracy is not None:
            parts.append(self.scalar_accuracy)
        if self.lists:
            parts.append(sum(s.f1 for s in self.lists.values()) / len(self.lists))
        return sum(parts) / len(parts) if parts else None

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "confidence_score": self.confidence_score,
            "review_decision": self.review_decision,
            "scalar_accuracy": self.scalar_accuracy,
            "doc_score": self.doc_score,
            "scalars": {k: v.value for k, v in self.scalars.items()},
            "lists": {k: v.to_dict() for k, v in self.lists.items()},
            "statute_verification": self.statute_verification,
            "retry_counts": self.retry_counts,
            "sourced_values": self.sourced_values,
            "sourced_values_with_chunk": self.sourced_values_with_chunk,
        }


def _count_sources(obj: Any) -> tuple[int, int]:
    """(values carrying sources, of those how many point at a chunk) — walks the model."""
    total = with_chunk = 0
    if isinstance(obj, list):
        for item in obj:
            t, w = _count_sources(item)
            total, with_chunk = total + t, with_chunk + w
        return total, with_chunk
    if isinstance(obj, BaseModel):
        sources = getattr(obj, "sources", None)
        if isinstance(sources, list):
            if sources:
                return 1, int(any(s.chunk_id for s in sources))
            return 0, 0
        for name in type(obj).model_fields:
            t, w = _count_sources(getattr(obj, name))
            total, with_chunk = total + t, with_chunk + w
    return total, with_chunk


def score_document(gold: GoldJudgment, pred: StructuredJudgment) -> DocumentScore:
    labelled = gold.labelled()
    score = DocumentScore(
        case_id=gold.case_id,
        confidence_score=pred.confidence.score,
        review_decision=pred.review_decision.value,
        retry_counts=dict(pred.processing.retry_counts),
    )

    pred_scalars = predicted_scalars(pred)
    for name in SCALAR_FIELDS:
        if name in labelled:
            score.scalars[name] = score_scalar(
                getattr(gold.metadata, name), pred_scalars[name], SCALAR_MATCHERS[name]
            )

    p_lists, g_lists = predicted_lists(pred), gold_lists(gold)
    for name in LIST_FIELDS:
        if name in labelled:
            score.lists[name] = score_list(g_lists[name], p_lists[name], LIST_MATCHERS[name])

    score.statute_verification = dict(Counter(r.verification_status.value for r in pred.statutes.references))
    for part in (pred.metadata, pred.facts, pred.statutes, pred.petitioner, pred.respondent, pred.evidence):
        t, w = _count_sources(part)
        score.sourced_values += t
        score.sourced_values_with_chunk += w
    return score


# --------------------------------------------------------------------------- aggregate


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _outcome_summary(outcomes: list[Outcome]) -> dict:
    c = Counter(outcomes)
    answered = c[Outcome.CORRECT] + c[Outcome.WRONG] + c[Outcome.SPURIOUS]
    gold_present = c[Outcome.CORRECT] + c[Outcome.WRONG] + c[Outcome.MISSED]
    return {
        "n": len(outcomes),
        "counts": {o.value: c[o] for o in Outcome},
        # Share of all labelled fields handled correctly (incl. correctly returning None).
        "accuracy": _rate(c[Outcome.CORRECT] + c[Outcome.CORRECT_ABSENT], len(outcomes)),
        # When the pipeline gave a value, how often it was wrong or invented.
        "error_rate_when_answered": _rate(c[Outcome.WRONG] + c[Outcome.SPURIOUS], answered),
        # When the judgment had the value, how often the pipeline returned None.
        "abstention_rate": _rate(c[Outcome.MISSED], gold_present),
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def aggregate(scores: list[DocumentScore]) -> dict:
    per_field: dict[str, list[Outcome]] = {}
    lists: dict[str, ListScore] = {}
    verification: Counter = Counter()
    decisions: dict[str, list[float]] = {}
    retries: dict[str, list[int]] = {}
    sourced = sourced_with_chunk = 0

    for s in scores:
        for name, outcome in s.scalars.items():
            per_field.setdefault(name, []).append(outcome)
        for name, ls in s.lists.items():
            lists.setdefault(name, ListScore())
            lists[name] += ls
        verification.update(s.statute_verification)
        if s.doc_score is not None:
            decisions.setdefault(s.review_decision, []).append(s.doc_score)
        for agent, n in s.retry_counts.items():
            retries.setdefault(agent, []).append(n)
        sourced += s.sourced_values
        sourced_with_chunk += s.sourced_values_with_chunk

    all_outcomes = [o for outcomes in per_field.values() for o in outcomes]
    statutes = lists.get("statutes")
    calibrated = [s for s in scores if s.doc_score is not None]

    return {
        "scalar_overall": _outcome_summary(all_outcomes),
        "scalar_fields": {name: _outcome_summary(outcomes) for name, outcomes in per_field.items()},
        "list_fields": {name: ls.to_dict() for name, ls in lists.items()},
        "statutes": {
            "extraction": statutes.to_dict() if statutes else None,
            "verification_status_counts": dict(verification),
        },
        "calibration": {
            # Does a higher confidence score actually mean a more accurate record?
            "pearson_confidence_vs_doc_score": _pearson(
                [s.confidence_score for s in calibrated], [s.doc_score for s in calibrated]
            ),
            "by_review_decision": {
                decision: {"documents": len(v), "mean_doc_score": sum(v) / len(v)}
                for decision, v in sorted(decisions.items())
            },
        },
        "retries": {agent: {"mean": sum(v) / len(v), "max": max(v)} for agent, v in sorted(retries.items())},
        "provenance": {
            "sourced_values": sourced,
            "with_chunk_id": sourced_with_chunk,
            "rate": _rate(sourced_with_chunk, sourced),
        },
    }

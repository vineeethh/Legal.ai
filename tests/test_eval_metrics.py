"""Evaluation scoring rules. Pure Python — runs without Docling, torch or an LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.gold import GoldJudgment, load_gold_dir
from evaluation.metrics import (
    Outcome,
    case_number_match,
    normalize_label,
    normalize_section,
    person_match,
    score_list,
    score_scalar,
    text_match,
)
from evaluation.run_eval import build_report, render_markdown

EXAMPLES = Path(__file__).resolve().parent.parent / "evaluation" / "examples"


@pytest.mark.parametrize(
    ("gold", "pred", "expected"),
    [
        ("High Court of Karnataka", "High Court of Karnataka at Bengaluru", True),
        ("High Court of Karnataka", "High Court of Kerala", False),
        ("Division Bench", "division  bench.", True),
    ],
)
def test_text_match(gold, pred, expected):
    assert text_match(gold, pred) is expected


def test_person_match_ignores_honorifics():
    assert person_match("Hon'ble Mr. Justice A. R. Menon", "A. R. Menon, J.")
    assert not person_match("Justice A. R. Menon", "Justice S. K. Rao")


def test_case_number_match_by_numbers():
    assert case_number_match("Criminal Appeal No. 412 of 2018", "Crl.A. 412/2018")
    assert not case_number_match("Criminal Appeal No. 412 of 2018", "Crl.A. 413/2018")


def test_normalizers():
    assert normalize_section("Section 304-B") == normalize_section("304 B") == "304b"
    assert normalize_label("Ext. P-5") == normalize_label("Ex.P5") == normalize_label("Exhibit P 5")
    assert normalize_label("PW-1") == "pw1"


@pytest.mark.parametrize(
    ("gold", "pred", "outcome"),
    [
        ("x", "x", Outcome.CORRECT),
        ("x", None, Outcome.MISSED),
        ("x", "y", Outcome.WRONG),
        (None, None, Outcome.CORRECT_ABSENT),
        (None, "y", Outcome.SPURIOUS),
    ],
)
def test_score_scalar_outcomes(gold, pred, outcome):
    assert score_scalar(gold, pred, lambda g, p: g == p) is outcome


def test_score_list_is_one_to_one():
    # Two predictions of the same item can only claim one gold item.
    score = score_list(["a"], ["a", "a"], lambda g, p: g == p)
    assert (score.tp, score.fp, score.fn) == (1, 1, 0)
    assert score.precision == 0.5 and score.recall == 1.0


def test_empty_list_scores_perfect():
    assert score_list([], [], lambda g, p: g == p).f1 == 1.0


def test_unlabelled_fields_are_skipped():
    gold = GoldJudgment.model_validate({"case_id": "c", "pdf": "x.pdf", "metadata": {"court": "X", "bench": None}})
    assert gold.labelled() == {"court", "bench"}


def test_example_report_numbers():
    golds = load_gold_dir(EXAMPLES / "gold")
    report = build_report(golds, EXAMPLES / "predictions", gold_dir=EXAMPLES / "gold", run_info=[])

    assert report["run"]["synthetic"] is True
    assert report["run"]["documents_scored"] == 2

    overall = report["summary"]["scalar_overall"]
    assert overall["counts"] == {"correct": 7, "correct_absent": 0, "missed": 1, "wrong": 0, "spurious": 1}
    assert overall["accuracy"] == pytest.approx(7 / 9)

    statutes = report["summary"]["list_fields"]["statutes"]
    assert (statutes["tp"], statutes["fp"], statutes["fn"]) == (7, 1, 1)

    evidence = report["summary"]["list_fields"]["evidence_labels"]
    assert (evidence["tp"], evidence["fn"]) == (4, 1)

    assert "Synthetic data" in render_markdown(report)

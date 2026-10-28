"""Evaluation CLI.

Score existing predictions (no heavy dependencies needed):

    python -m evaluation.run_eval --gold evaluation/gold --predictions evaluation/predictions

Run the real pipeline first for any gold file without a prediction (needs the
full Docker environment), then score:

    docker compose run --rm app python -m evaluation.run_eval --run

A prediction is the StructuredJudgment JSON for one case, saved as
<predictions>/<case_id>.json — exactly what `python -m pipeline.run x.pdf --out`
writes. Reports go to evaluation/reports/<name>.json (+ .md), where the API's
/api/eval endpoints and the UI's Evaluation page pick them up.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from schemas import StructuredJudgment

from .gold import GoldJudgment, load_gold_dir
from .metrics import aggregate, score_document

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLD = REPO_ROOT / "evaluation" / "gold"
DEFAULT_PREDICTIONS = REPO_ROOT / "evaluation" / "predictions"
DEFAULT_REPORTS = REPO_ROOT / "evaluation" / "reports"


def run_pipeline(gold: GoldJudgment, *, save_to_db: bool) -> tuple[dict | None, dict]:
    """Runs the real pipeline on one gold PDF. Returns (prediction JSON or None, run info).

    Human review is auto-approved so the report measures what the pipeline
    produced on its own; the info dict records that review was requested.
    """
    from observability import traced_run_config
    from pipeline.graph import run_document
    from pipeline.pdf_safety import PdfSafetyError
    from pipeline.persistence import save_run

    pdf_path = REPO_ROOT / gold.pdf
    if not pdf_path.exists():
        return None, {"case_id": gold.case_id, "status": "pdf_missing", "pdf": gold.pdf}

    document_id = f"eval-{gold.case_id}-{uuid.uuid4().hex[:8]}"
    reviews: list[dict] = []

    def auto_approve(payload: dict) -> dict:
        reviews.append(payload)
        return {"action": "approve"}

    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        state, decision = run_document(
            document_id,
            str(pdf_path),
            run_config=traced_run_config(session_id=document_id, tags=["eval"]),
            on_human_review=auto_approve,
        )
    except PdfSafetyError as exc:
        return None, {"case_id": gold.case_id, "status": "rejected", "reasons": exc.reasons}

    if save_to_db:
        save_run(state, started_at=started_at, langfuse_session_id=document_id, human_review_decision=decision)
    info = {"case_id": gold.case_id, "status": "ok", "review_requested": bool(reviews), "document_id": document_id}
    return state.result.model_dump(mode="json"), info


def build_report(
    golds: list[GoldJudgment],
    predictions_dir: Path,
    *,
    gold_dir: Path,
    run_info: list[dict],
) -> dict:
    scores = []
    missing = []
    models = set()
    for gold in golds:
        path = predictions_dir / f"{gold.case_id}.json"
        if not path.exists():
            missing.append(gold.case_id)
            continue
        pred = StructuredJudgment.model_validate_json(path.read_text())
        models.add(pred.processing.llm_model)
        scores.append(score_document(gold, pred))

    return {
        "run": {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "gold_dir": str(gold_dir),
            "predictions_dir": str(predictions_dir),
            "documents_labelled": len(golds),
            "documents_scored": len(scores),
            "missing_predictions": missing,
            "pipeline_runs": run_info,
            "llm_models": sorted(models),
            "synthetic": any(g.synthetic for g in golds),
        },
        "summary": aggregate(scores),
        "documents": [s.to_dict() for s in scores],
    }


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: dict) -> str:
    run, summary = report["run"], report["summary"]
    overall = summary["scalar_overall"]
    lines = [f"# Evaluation report — {run['created_at']}", ""]
    if run["synthetic"]:
        lines += ["> **Synthetic data.** These numbers come from made-up examples and say nothing about real accuracy.", ""]
    lines += [
        f"- Documents scored: **{run['documents_scored']}** of {run['documents_labelled']} labelled"
        + (f" (missing predictions: {', '.join(run['missing_predictions'])})" if run["missing_predictions"] else ""),
        f"- Models: {', '.join(run['llm_models']) or '—'}",
        "",
        "## Headline numbers",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Scalar field accuracy | {_pct(overall['accuracy'])} |",
        f"| Error rate when the pipeline answered | {_pct(overall['error_rate_when_answered'])} |",
        f"| Abstention rate (returned None, value existed) | {_pct(overall['abstention_rate'])} |",
    ]
    statutes = summary["statutes"]["extraction"]
    if statutes:
        lines.append(f"| Statute citations F1 | {_pct(statutes['f1'])} |")
    lines.append(f"| Values traceable to a chunk | {_pct(summary['provenance']['rate'])} |")

    lines += ["", "## Scalar fields", "", "| Field | n | Accuracy | Error when answered | Abstained |", "|---|---|---|---|---|"]
    for name, s in summary["scalar_fields"].items():
        lines.append(
            f"| {name} | {s['n']} | {_pct(s['accuracy'])} | {_pct(s['error_rate_when_answered'])} | {_pct(s['abstention_rate'])} |"
        )

    lines += ["", "## List fields", "", "| Field | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for name, s in summary["list_fields"].items():
        lines.append(
            f"| {name} | {s['tp']} | {s['fp']} | {s['fn']} | {_pct(s['precision'])} | {_pct(s['recall'])} | {_pct(s['f1'])} |"
        )

    cal = summary["calibration"]
    r = cal["pearson_confidence_vs_doc_score"]
    lines += [
        "",
        "## Is the confidence score trustworthy?",
        "",
        f"Pearson correlation between confidence and per-document score: **{'—' if r is None else f'{r:.2f}'}**"
        + (" (needs at least 3 documents with varying scores)" if r is None else ""),
        "",
        "| Review decision | Documents | Mean document score |",
        "|---|---|---|",
    ]
    for decision, row in cal["by_review_decision"].items():
        lines.append(f"| {decision} | {row['documents']} | {_pct(row['mean_doc_score'])} |")

    lines += ["", "## Per document", "", "| Case | Confidence | Decision | Scalar accuracy | Doc score |", "|---|---|---|---|---|"]
    for d in report["documents"]:
        lines.append(
            f"| {d['case_id']} | {d['confidence_score']:.3f} | {d['review_decision']} | {_pct(d['scalar_accuracy'])} | {_pct(d['doc_score'])} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score pipeline outputs against gold labels.")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD, help="Directory of gold *.json files.")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS, help="Directory of <case_id>.json predictions.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS, help="Where to write the report.")
    parser.add_argument("--name", help="Report file name (default: UTC timestamp).")
    parser.add_argument("--run", action="store_true", help="Run the pipeline for gold files with no prediction yet.")
    parser.add_argument("--rerun", action="store_true", help="With --run: re-run even if a prediction exists.")
    parser.add_argument("--save-to-db", action="store_true", help="With --run: also persist runs to Postgres.")
    args = parser.parse_args(argv)

    golds = load_gold_dir(args.gold)
    if not golds:
        print(f"No gold files in {args.gold} (files starting with '_' are templates and are skipped).", file=sys.stderr)
        return 1

    run_info: list[dict] = []
    if args.run:
        args.predictions.mkdir(parents=True, exist_ok=True)
        for gold in golds:
            out = args.predictions / f"{gold.case_id}.json"
            if out.exists() and not args.rerun:
                continue
            print(f"Running pipeline on {gold.case_id} ...", file=sys.stderr)
            prediction, info = run_pipeline(gold, save_to_db=args.save_to_db)
            run_info.append(info)
            if prediction is not None:
                out.write_text(json.dumps(prediction, indent=2))

    report = build_report(golds, args.predictions, gold_dir=args.gold, run_info=run_info)
    name = args.name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{name}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    markdown = render_markdown(report)
    (args.out_dir / f"{name}.md").write_text(markdown)

    print(markdown)
    print(f"Wrote {json_path} and {json_path.with_suffix('.md')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""CLI entrypoint: python -m pipeline.run <judgment.pdf>

Runs the full pipeline against one PDF, prints the structured result, and
persists it to Postgres. Tracing is attached via a Langfuse session keyed to
the document id so every agent + retry lands under one trace.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path


def _cli_human_review(payload: dict) -> dict:
    """Default on_human_review callback: prompts on the terminal.

    Runs whenever confidence routes to `human_required` (score < 0.80). Prints
    the flagged fields + assembled result preview to stderr, then asks the
    reviewer to approve, reject, or edit (via a JSON patch file) before the
    graph resumes and the record is persisted.
    """
    print("\n--- Human review required ---", file=sys.stderr)
    print(f"document_id={payload['document_id']} confidence={payload['confidence_score']:.3f}", file=sys.stderr)
    print("Flagged fields:", file=sys.stderr)
    for field in payload["flagged_fields"]:
        print(f"  [{field['agent']}] {field['field_path']}: {field['reason']}", file=sys.stderr)
    print("\nResult preview:", file=sys.stderr)
    print(json.dumps(payload["result_preview"], indent=2), file=sys.stderr)

    while True:
        choice = input("\nApprove and save / Reject / Edit via JSON patch file [a/r/e]? ").strip().lower()
        if choice == "a":
            return {"action": "approve"}
        if choice == "r":
            return {"action": "reject"}
        if choice == "e":
            patch_path = input("Path to JSON patch file (top-level field overrides): ").strip()
            patches = json.loads(Path(patch_path).read_text())
            return {"action": "edit", "patches": patches}
        print("Please enter 'a', 'r', or 'e'.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Legal AI extraction pipeline on one judgment PDF.")
    parser.add_argument("pdf_path", help="Path to the judgment PDF.")
    parser.add_argument("--no-save", action="store_true", help="Skip writing the result to Postgres.")
    parser.add_argument("--out", help="Optional path to also write the structured JSON to disk.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Imported lazily so `--help` doesn't require every dependency installed.
    from observability import traced_run_config, verify_langfuse_connection

    from .graph import run_document
    from .pdf_safety import PdfSafetyError
    from .persistence import save_run

    document_id = str(uuid.uuid4())
    verify_langfuse_connection()

    started_at = datetime.utcnow()
    print(f"Processing {pdf_path.name} (document_id={document_id}) ...")

    run_config = traced_run_config(session_id=document_id, tags=["cli"])
    try:
        state, human_review_decision = run_document(
            document_id, str(pdf_path), run_config=run_config, on_human_review=_cli_human_review
        )
    except PdfSafetyError as exc:
        print(f"Rejected {pdf_path.name}: {'; '.join(exc.reasons)}", file=sys.stderr)
        sys.exit(1)

    result_json = state.result.model_dump(mode="json")
    print(json.dumps(result_json, indent=2))
    print(
        f"\nConfidence: {state.result.confidence.score:.3f} -> {state.result.review_decision.value}",
        file=sys.stderr,
    )

    if args.out:
        Path(args.out).write_text(json.dumps(result_json, indent=2))
        print(f"Wrote {args.out}", file=sys.stderr)

    if not args.no_save:
        run_id = save_run(
            state,
            started_at=started_at,
            langfuse_session_id=document_id,
            human_review_decision=human_review_decision,
        )
        print(f"Saved processing_runs.id={run_id}", file=sys.stderr)


if __name__ == "__main__":
    main()

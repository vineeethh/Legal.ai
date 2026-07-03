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
    from .persistence import save_run

    document_id = str(uuid.uuid4())
    verify_langfuse_connection()

    started_at = datetime.utcnow()
    print(f"Processing {pdf_path.name} (document_id={document_id}) ...")

    run_config = traced_run_config(session_id=document_id, tags=["cli"])
    state = run_document(document_id, str(pdf_path), run_config=run_config)

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
        run_id = save_run(state, started_at=started_at, langfuse_session_id=document_id)
        print(f"Saved processing_runs.id={run_id}", file=sys.stderr)


if __name__ == "__main__":
    main()

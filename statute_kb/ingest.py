"""KB ingestion: data/raw/<act>/*.pdf -> data/processed/<version>.jsonl -> Postgres + Qdrant.

Run as: python -m statute_kb.ingest [--acts IPC,BNS,...] [--skip-qdrant]

Re-run whenever an act PDF changes or a new act version needs to be added.
Postgres rows are upserted on (act, act_version, section_number); Qdrant
points are upserted on the same composite key (deterministic UUID5).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import psycopg
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from pipeline.config import get_settings
from pipeline.docling_parse import parse_pdf
from statute_kb.acts import ACT_REGISTRY, ActEntry
from statute_kb.parser import coverage_report, split_into_sections

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
POINT_NAMESPACE = uuid.UUID("6e6f8f0a-5b34-4e2a-9a2e-9b6a7b6a2b1a")


def _point_id(act_version: str, section_number: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, f"{act_version}:{section_number}"))


def process_act(entry: ActEntry) -> Path:
    pdf_path = REPO_ROOT / entry.pdf_path
    if not pdf_path.exists():
        raise FileNotFoundError(f"{entry.act_version}: PDF not found at {pdf_path}")

    print(f"[{entry.act_version}] parsing {pdf_path.name} ...")
    parsed = parse_pdf(pdf_path)
    print(f"[{entry.act_version}] {len(parsed.sections)} heading-groups, ocr_used={parsed.ocr_used}")

    raw_sections = split_into_sections(parsed)
    print(f"[{entry.act_version}] {len(raw_sections)} sections extracted")

    report = coverage_report(raw_sections)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    report_path = PROCESSED_DIR / f"{entry.act_version}.report.json"
    report_path.write_text(json.dumps(report, indent=2))
    if report["missing_numbers_in_range"]:
        print(
            f"[{entry.act_version}] WARNING: {len(report['missing_numbers_in_range'])} "
            f"possible gaps — see {report_path.name}"
        )

    out_path = PROCESSED_DIR / f"{entry.act_version}.jsonl"
    with out_path.open("w") as f:
        for s in raw_sections:
            record = {
                "act": entry.act.value,
                "act_family": entry.act_family.value,
                "act_version": entry.act_version,
                "section_number": s.section_number,
                "section_title": s.section_title,
                "chapter_path": s.chapter_path,
                "content": s.content,
                "status": entry.status,
                "effective_from": entry.effective_from.isoformat(),
                "effective_to": entry.effective_to.isoformat() if entry.effective_to else None,
                "source_citation": entry.source_citation,
                "qdrant_point_id": _point_id(entry.act_version, s.section_number),
            }
            f.write(json.dumps(record) + "\n")

    print(f"[{entry.act_version}] wrote {out_path}")
    return out_path


def load_postgres(jsonl_path: Path) -> int:
    settings = get_settings()
    records = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    if not records:
        return 0

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for r in records:
                cur.execute(
                    """
                    INSERT INTO statute_sections
                        (act, act_family, act_version, section_number, section_title,
                         chapter_path, content, status, effective_from, effective_to,
                         source_citation, qdrant_point_id)
                    VALUES (%(act)s, %(act_family)s, %(act_version)s, %(section_number)s,
                            %(section_title)s, %(chapter_path)s, %(content)s, %(status)s,
                            %(effective_from)s, %(effective_to)s, %(source_citation)s,
                            %(qdrant_point_id)s)
                    ON CONFLICT (act, act_version, section_number) DO UPDATE SET
                        section_title = EXCLUDED.section_title,
                        chapter_path = EXCLUDED.chapter_path,
                        content = EXCLUDED.content,
                        status = EXCLUDED.status,
                        effective_from = EXCLUDED.effective_from,
                        effective_to = EXCLUDED.effective_to,
                        source_citation = EXCLUDED.source_citation,
                        qdrant_point_id = EXCLUDED.qdrant_point_id
                    """,
                    r,
                )
        conn.commit()
    return len(records)


def load_qdrant(jsonl_path: Path) -> int:
    from pipeline.embeddings import embed_texts

    settings = get_settings()
    records = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    if not records:
        return 0

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )

    texts = [f"{r['section_title']}\n{r['content']}" for r in records]
    vectors = embed_texts(texts)

    points = [
        PointStruct(
            id=r["qdrant_point_id"],
            vector=vectors[i].tolist(),
            payload={k: v for k, v in r.items() if k != "qdrant_point_id"},
        )
        for i, r in enumerate(records)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    return len(points)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest bare-act PDFs into the statute KB.")
    parser.add_argument("--acts", help="Comma-separated act_version values to limit to (default: all)")
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help=(
            "Skip Docling parsing entirely and load Qdrant from an existing "
            "data/processed/<version>.jsonl. Run this as a separate container "
            "invocation from the parse+Postgres step — docling's layout/OCR "
            "models and the BGE-M3 embedding model together can exceed a "
            "constrained container's memory if loaded in the same process."
        ),
    )
    parser.add_argument(
        "--postgres-only",
        action="store_true",
        help=(
            "Skip Docling parsing entirely and load Postgres (the Tier-1 "
            "verification source) from an existing data/processed/<version>.jsonl. "
            "The symmetric counterpart to --embed-only, so the KB can be populated "
            "from the committed seed JSONL without needing the raw act PDFs. Loads "
            "no ML models, so it is fast and light."
        ),
    )
    args = parser.parse_args()

    wanted = set(args.acts.split(",")) if args.acts else None
    entries = [e for e in ACT_REGISTRY if wanted is None or e.act_version in wanted]
    if not entries:
        print("No matching acts in registry.", file=sys.stderr)
        sys.exit(1)

    if args.postgres_only:
        for entry in entries:
            jsonl_path = PROCESSED_DIR / f"{entry.act_version}.jsonl"
            if not jsonl_path.exists():
                print(f"SKIP: {jsonl_path} not found — run the parse step first.", file=sys.stderr)
                continue
            n = load_postgres(jsonl_path)
            print(f"[{entry.act_version}] upserted {n} rows into Postgres")
        return

    if args.embed_only:
        for entry in entries:
            jsonl_path = PROCESSED_DIR / f"{entry.act_version}.jsonl"
            if not jsonl_path.exists():
                print(f"SKIP: {jsonl_path} not found — run the parse step first.", file=sys.stderr)
                continue
            n = load_qdrant(jsonl_path)
            print(f"[{entry.act_version}] upserted {n} points into Qdrant")
        return

    for entry in entries:
        try:
            jsonl_path = process_act(entry)
        except FileNotFoundError as e:
            print(f"SKIP: {e}", file=sys.stderr)
            continue

        if not args.skip_postgres:
            n = load_postgres(jsonl_path)
            print(f"[{entry.act_version}] upserted {n} rows into Postgres")

        if not args.skip_qdrant:
            n = load_qdrant(jsonl_path)
            print(f"[{entry.act_version}] upserted {n} points into Qdrant")


if __name__ == "__main__":
    main()

"""Loader for the old-act -> new-act crosswalk (statute_mappings table).

Deliberately NOT auto-populated from an LLM or inferred from embeddings —
section renumbering is not 1:1 (splits, merges, net-new offenses, dropped
provisions), so wrong entries here would silently misinform every citation
that uses `current_equivalent`. Populate data/processed/statute_mappings_seed.csv
from an authoritative source (the MHA's published IPC/CrPC/Evidence Act to
BNS/BNSS/BSA concordance tables, or PRS India's summaries of the same) and
run this loader — do not hand-type mappings from memory.

CSV columns: old_act,old_section,new_act,new_section,mapping_type,notes
mapping_type in: exact | split | merged | renumbered | new_provision | no_equivalent
"""

from __future__ import annotations

import csv
from pathlib import Path

import psycopg

from pipeline.config import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_CSV = REPO_ROOT / "data" / "processed" / "statute_mappings_seed.csv"

VALID_MAPPING_TYPES = {"exact", "split", "merged", "renumbered", "new_provision", "no_equivalent"}


def load_mappings(csv_path: Path = SEED_CSV) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"No mapping seed file at {csv_path}")

    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print(f"{csv_path} has no rows yet — nothing to load. See statute_kb/mappings.py docstring.")
        return 0

    for r in rows:
        if r["mapping_type"] not in VALID_MAPPING_TYPES:
            raise ValueError(f"Invalid mapping_type '{r['mapping_type']}' in row: {r}")

    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO statute_mappings (old_act, old_section, new_act, new_section, mapping_type, notes)
                    VALUES (%(old_act)s, %(old_section)s, %(new_act)s, %(new_section)s, %(mapping_type)s, %(notes)s)
                    """,
                    r,
                )
        conn.commit()

    print(f"Loaded {len(rows)} mappings from {csv_path}")
    return len(rows)


if __name__ == "__main__":
    load_mappings()

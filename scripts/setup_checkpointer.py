"""One-shot: create langgraph-checkpoint-postgres's tables.

Run once against the database (mirrors applying db/schema.sql once) — not
called per-document from pipeline/graph.py, since it's DDL.

    python -m scripts.setup_checkpointer
"""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver

from pipeline.config import get_settings


def main() -> None:
    settings = get_settings()
    with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        checkpointer.setup()
    print("Checkpointer tables ready.")


if __name__ == "__main__":
    main()

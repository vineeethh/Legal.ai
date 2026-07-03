"""Applies db/schema.sql to DATABASE_URL. Idempotent (CREATE TABLE IF NOT EXISTS)."""

from __future__ import annotations

from pathlib import Path

import psycopg

from pipeline.config import get_settings


def main() -> None:
    schema_sql = (Path(__file__).parent / "schema.sql").read_text()
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    print("Schema applied.")


if __name__ == "__main__":
    main()

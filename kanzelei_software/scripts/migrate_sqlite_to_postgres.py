"""
SQLite -> PostgreSQL Migration (Kanzlei AI)

Usage:
  python scripts/migrate_sqlite_to_postgres.py \
    --sqlite data/kanzlei.db \
    --pg "postgresql://user:pass@host:5432/dbname"

Hinweis:
- Erwartet Zieltabellen laut scripts/postgres_bootstrap.sql
- Führt idempotente upserts aus (wo möglich)
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import Iterable, Sequence

import psycopg2
from psycopg2.extras import execute_batch


TABLES = [
    "kanzleien",
    "benutzer",
    "mandanten",
    "aufgaben",
    "kommunikation",
    "audit_log",
    "email_outbox",
]


def rows_from_sqlite(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple]]:
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


def copy_table(pg_conn, table: str, cols: Sequence[str], rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)

    if table == "audit_log":
        sql = f"""
            INSERT INTO {table} ({col_list})
            VALUES ({placeholders})
        """
    elif "id" in cols:
        sql = f"""
            INSERT INTO {table} ({col_list})
            VALUES ({placeholders})
            ON CONFLICT (id) DO NOTHING
        """
    else:
        sql = f"""
            INSERT INTO {table} ({col_list})
            VALUES ({placeholders})
        """
    with pg_conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=500)
    pg_conn.commit()
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="Pfad zur SQLite DB")
    ap.add_argument("--pg", required=True, help="PostgreSQL DSN")
    args = ap.parse_args()

    sconn = sqlite3.connect(args.sqlite)
    sconn.row_factory = sqlite3.Row

    pconn = psycopg2.connect(args.pg)
    pconn.autocommit = False

    total = 0
    for t in TABLES:
        cols, rows = rows_from_sqlite(sconn, t)
        n = copy_table(pconn, t, cols, rows)
        total += n
        print(f"[OK] {t}: {n} rows")

    print(f"\nMigration abgeschlossen. Gesamt: {total} rows.")


if __name__ == "__main__":
    main()

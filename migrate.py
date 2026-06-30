#!/usr/bin/env python3
"""
Lightweight migration runner.

- Each file in migrations/ is named NNNN_description.sql and applied in order.
- Applied migrations are recorded in schema_migrations so they never re-run.
- Safe to run repeatedly: `python3 migrate.py --db chess.db`
"""
import argparse
import pathlib
import sqlite3
import sys

import db

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def migrate(db_path: str):
    conn = db.get_connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    pending = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.stem not in applied)
    if not pending:
        print("Nothing to do — database is up to date.")
        return

    for path in pending:
        print(f"Applying {path.name} ...")
        sql = path.read_text()
        try:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (path.stem,))
            conn.commit()
        except sqlite3.OperationalError as e:
            conn.rollback()
            # raise, not sys.exit() -- sys.exit() raises SystemExit, a
            # BaseException an in-process caller's `except Exception` (e.g.
            # the Settings-page database-import feature) would NOT catch.
            # Same bug class worker.run()'s missing-engine case already hit
            # and fixed once (BRIEF.md Phase C) -- fixed the same way here,
            # not freshly invented.
            raise RuntimeError(f"Migration {path.name} failed: {e}") from e
    print(f"Applied {len(pending)} migration(s). Database is up to date.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="chess.db")
    args = ap.parse_args()
    try:
        migrate(args.db)
    except RuntimeError as e:
        print(f"  FAILED: {e}", file=sys.stderr)
        print("  Stopping — fix the migration before continuing.", file=sys.stderr)
        sys.exit(1)

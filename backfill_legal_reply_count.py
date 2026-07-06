#!/usr/bin/env python3
"""
One-time backfill: legal_reply_count for zero-time moves ingested before
migrations/0032 added the column (ingest.py populates it going forward).

Depends only on fen_before (present for every move since ingest.py's first
version) and time_spent_seconds -- no Stockfish analysis required, unlike
motif's backfill (which piggybacks on re-running annotate.py). Safe to
re-run: only touches rows where legal_reply_count IS NULL.

Usage:
    python3 backfill_legal_reply_count.py
"""
import argparse
import sys

import chess

from migrate import migrate
from db import get_connection
from config import load_config, pick

BATCH_SIZE = 5000


def backfill(db_path: str):
    migrate(db_path)
    conn = get_connection(db_path)

    rows = conn.execute("""
        SELECT id, fen_before FROM moves
        WHERE time_spent_seconds = 0 AND legal_reply_count IS NULL AND fen_before IS NOT NULL
    """).fetchall()
    print(f"Backfilling legal_reply_count for {len(rows)} move(s)...")

    updates = []
    failed = 0
    for move_id, fen_before in rows:
        try:
            count = chess.Board(fen_before).legal_moves.count()
        except Exception as e:
            # a malformed fen_before shouldn't abort the whole backfill --
            # same one-bad-row isolation as ingest.py/annotate.py's per-game try/except
            failed += 1
            print(f"  WARNING: skipped move {move_id} (bad fen_before): {e}", file=sys.stderr)
            continue
        updates.append((count, move_id))
        if len(updates) >= BATCH_SIZE:
            conn.executemany("UPDATE moves SET legal_reply_count=? WHERE id=?", updates)
            conn.commit()
            updates = []

    if updates:
        conn.executemany("UPDATE moves SET legal_reply_count=? WHERE id=?", updates)
        conn.commit()

    print(f"Done: {len(rows) - failed} move(s) updated.")
    if failed:
        print(f"Skipped {failed} move(s) due to errors -- see warnings above.", file=sys.stderr)
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    backfill(db_path)

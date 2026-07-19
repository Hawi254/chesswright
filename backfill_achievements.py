#!/usr/bin/env python3
"""
One-time (but safe to re-run) sweep: evaluates the full Achievements
Service catalog against ALL existing history, regardless of each
achievement's declared `triggers` -- so achievements already earned by
past games/reviews unlock immediately once this service is deployed,
rather than only reacting to games synced or analyzed after this ships.

Idempotent: achievements.evaluate() only ever inserts a row for an
achievement not already in achievements_unlocked, so re-running finds
nothing new the second time.

Usage:
    python3 backfill_achievements.py
"""
import argparse

from migrate import migrate
from db import get_connection
from config import load_config, pick
import achievements


def backfill(db_path: str, config_path=None):
    migrate(db_path)
    conn = get_connection(db_path)
    newly_unlocked = achievements.evaluate(conn, trigger=None, config_path=config_path)
    conn.close()
    if newly_unlocked:
        print(f"Unlocked {len(newly_unlocked)} achievement(s): {newly_unlocked}")
    else:
        print("No new achievements unlocked.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    backfill(db_path, config_path=args.config)

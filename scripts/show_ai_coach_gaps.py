#!/usr/bin/env python3
"""Print the AI Coach capability-gap backlog: every turn where Claude
itself reported it couldn't fully answer a question using its available
tools (see chesswright_pro/ai_coach.py's report_capability_gap tool and
dashboard/data/ai_coach.py's record_capability_gap/get_capability_gaps).

This is the actual mechanism that replaces ai_coach_gap_watch's manual
tool-table re-audit with "run this script, read a short real list" --
deliberately minimal, no new Settings-page UI section (see the Phase 3
plan's §3.7: an in-app export button is a separate, not-yet-justified
follow-up).

Usage:
    python3 scripts/show_ai_coach_gaps.py
    python3 scripts/show_ai_coach_gaps.py --db /path/to/chess.db --limit 50
"""
import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from config import load_config, pick
from db import get_connection
import data


def _truncate(s: str, width: int) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= width else s[: width - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])

    conn = get_connection(db_path)
    try:
        gaps = data.get_capability_gaps(conn, limit=args.limit)
    finally:
        conn.close()

    if not gaps:
        print("No capability gaps logged yet.")
        return

    header = f"{'turn_id':>8}  {'created_at':<25}  {'question':<40}  missing_data"
    print(header)
    print("-" * len(header))
    for g in gaps:
        print(
            f"{g['turn_id']:>8}  {g['created_at']:<25}  "
            f"{_truncate(g['question_summary'], 40):<40}  "
            f"{_truncate(g['missing_data_description'], 60)}"
        )
    print(f"\n{len(gaps)} capability gap(s) shown (limit={args.limit}).")


if __name__ == "__main__":
    main()

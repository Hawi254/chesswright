#!/usr/bin/env python3
"""
One-time backfill: seeds `batch_eval_cache` (migrations/0033) from `moves`
rows analyzed BEFORE the eval-reuse-cache feature existed (see worker.py's
fetch_cached_eval()/store_cached_eval() and REUSE_EVAL_MAX_PLY). The cache
has been forward-filling since deploy -- every fresh engine run stores its
own result -- but historical rows never got a chance to populate it, so
early post-deploy batches only benefit from dedup among games analyzed
after the feature shipped. This backfill closes that gap once.

Candidates: moves with ply <= worker.REUSE_EVAL_MAX_PLY, non-null
fen_before, non-null engine_version, and a resolvable analysis_runs join
(depth/multipv come from analysis_runs, NOT moves.engine_depth -- that's
the engine's self-reported depth, which can legitimately differ from the
requested search depth that is actually part of the cache key). Grouped by
the exact cache key (fen_before, engine_version, depth, multipv); within a
group, the lowest moves.id wins (first-analyzed, deterministic tie-break
done in SQL via GROUP BY + MIN(m.id), not left to arbitrary row order).

Idempotent via the same INSERT OR IGNORE row-level mechanism the forward
(worker.py) path already uses -- store_cached_eval() is imported and
reused directly rather than reimplemented. Re-running produces zero new
rows the second time.

Usage:
    python3 backfill_batch_eval_cache.py
    python3 backfill_batch_eval_cache.py --db /path/to/chess.db
"""
import argparse
import json

from migrate import migrate
from db import get_connection
from config import load_config, pick
from worker import REUSE_EVAL_MAX_PLY, store_cached_eval

BATCH_SIZE = 5000

CANDIDATE_QUERY = """
SELECT ml.move_id, ml.pv_rank, ml.eval_cp, ml.eval_mate, ml.move_san, ml.pv_json, ml.score_is_exact,
       g.fen_before, g.engine_version, g.depth, g.multipv
FROM move_lines ml
JOIN (
    SELECT m.fen_before AS fen_before, m.engine_version AS engine_version,
           ar.depth AS depth, ar.multipv AS multipv, MIN(m.id) AS winner_id
    FROM moves m
    JOIN analysis_runs ar ON ar.id = m.analysis_run_id
    WHERE m.ply <= ? AND m.fen_before IS NOT NULL AND m.engine_version IS NOT NULL
      AND ar.depth IS NOT NULL AND ar.multipv IS NOT NULL
    GROUP BY m.fen_before, m.engine_version, ar.depth, ar.multipv
) g ON ml.move_id = g.winner_id
ORDER BY g.fen_before, g.engine_version, g.depth, g.multipv, ml.pv_rank
"""


def backfill(db_path: str):
    migrate(db_path)
    conn = get_connection(db_path)

    rows = conn.execute(CANDIDATE_QUERY, (REUSE_EVAL_MAX_PLY,)).fetchall()
    print(f"Candidates seen: {len(rows)} move_lines row(s) across winning moves "
          f"(ply <= {REUSE_EVAL_MAX_PLY}).")

    before_count = conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0]

    groups_seen = 0
    current_key = None
    current_payload = []
    since_commit = 0

    def flush_group():
        nonlocal since_commit
        if current_key is None:
            return
        fen_before, engine_version, depth, multipv = current_key
        store_cached_eval(conn, fen_before, engine_version, depth, multipv, current_payload)
        since_commit += 1
        if since_commit >= BATCH_SIZE:
            conn.commit()
            since_commit = 0

    for (_move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact,
         fen_before, engine_version, depth, multipv) in rows:
        key = (fen_before, engine_version, depth, multipv)
        if key != current_key:
            flush_group()
            groups_seen += 1
            current_key = key
            current_payload = []
        current_payload.append({
            "pv_rank": pv_rank,
            "eval_cp": eval_cp,
            "eval_mate": eval_mate,
            "move_san": move_san,
            "pv_san": json.loads(pv_json) if pv_json is not None else [],
            "score_is_exact": score_is_exact,
        })

    flush_group()  # final group
    conn.commit()

    after_count = conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0]
    inserted = after_count - before_count
    already_present = groups_seen - inserted

    print(f"Distinct cache-key groups: {groups_seen}")
    print(f"Rows inserted: {inserted}")
    print(f"Already present (no-op, idempotent re-run): {already_present}")
    print(f"batch_eval_cache total rows now: {after_count}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    backfill(db_path)

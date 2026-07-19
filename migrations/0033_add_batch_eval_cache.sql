-- Local FEN-keyed eval reuse cache for the batch worker. 70.0% of ply-1-20
-- move rows in the real dev DB are exact-FEN repeats of positions already
-- analyzed in another game (see explore/batch-cloud-eval's
-- DEDUP_CACHE_PLAN.md for the measurement) -- this table lets worker.py
-- reuse that prior result instead of re-running Stockfish.
--
-- Deliberately a NEW table, not a reuse of `position_cache` (0021): that
-- table is the dashboard's single-line, mixed-provenance on-demand tier
-- (dashboard/live_engine.py, dashboard/data/openings.py) and is never
-- touched by worker.py. This table is batch-only.
--
-- Key is the exact full FEN (counters included, no normalization) plus
-- engine_version/requested_depth/multipv -- an engine upgrade or config
-- change naturally stops reuse (a clean cache miss) instead of mixing
-- eval scales from different search configurations.
--
-- lines_json holds one JSON object per pv_rank (ascending), each with the
-- same fields worker.py's own INSERT OR REPLACE INTO move_lines writes
-- (eval_cp, eval_mate, move_san, pv_san as a list, score_is_exact) --
-- enough to reconstruct both the `moves` row (from the pv_rank=1 entry)
-- and every `move_lines` row on a cache hit, with no engine involved.
-- Telemetry describing the search itself (nodes/hashfull/tbhits/nps/
-- search_time_ms/engine_reported_time_ms/engine_depth/seldepth) is
-- intentionally NOT stored here -- a reused row leaves those NULL on
-- both `moves` and `move_lines`, since they describe a search that
-- didn't happen this time (worker.py itself is the only reader of any
-- of them; see CODEBASE_FACTS.md (d)).
CREATE TABLE IF NOT EXISTS batch_eval_cache (
    fen_before      TEXT    NOT NULL,
    engine_version  TEXT    NOT NULL,
    requested_depth INTEGER NOT NULL,
    multipv         INTEGER NOT NULL,
    lines_json      TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (fen_before, engine_version, requested_depth, multipv)
);

-- eval_source: 'engine' for a fresh Stockfish run, 'reuse' for a
-- batch_eval_cache hit. NULL on every row analyzed before this migration
-- (no backfill -- historical rows predate the concept of provenance).
ALTER TABLE moves ADD COLUMN eval_source TEXT;

-- Position analysis cache for on-demand interactive engine probes.
--
-- Kept separate from the moves table (batch worker results) to preserve
-- batch-result provenance -- moves.eval_cp carries engine_depth/version
-- metadata from a batch run; mixing in a quick 0.5s interactive probe
-- would conflate two different analysis quality levels.
--
-- get_position_analysis() checks moves first (authoritative), then here.
-- store_position_analysis() only writes here when depth >= store_threshold.
--
-- eval_cp follows the same convention as moves.eval_cp: from the
-- side-to-move's perspective (positive = the player about to move is
-- better). Matches the batch worker so get_position_analysis() can
-- return either source with the same interpretation.
CREATE TABLE IF NOT EXISTS position_cache (
    fen_before      TEXT    PRIMARY KEY,
    eval_cp         INTEGER,
    eval_mate       INTEGER,
    best_move_san   TEXT,
    pv_json         TEXT,
    engine_depth    INTEGER,
    engine_version  TEXT,
    analyzed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

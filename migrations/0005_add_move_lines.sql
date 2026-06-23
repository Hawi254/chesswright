-- Holds every MultiPV line returned by the engine (pv_rank 1..N).
-- moves.eval_cp/eval_mate/best_move_san/pv_json/nodes continue to mean
-- exactly what they did under single-line search (rank 1) -- this table
-- is purely additive, so nothing built on top of the existing columns
-- (Phase 3 CPL/classification plan) needs to change.
--
-- Feeds directly into goals discussed: rank1-vs-rank2 eval gap = "how
-- forced/unique was the best move" (sharpness, "great move", puzzle
-- candidates); rank among lines the played move matches = correctness
-- signal independent of raw CPL.
CREATE TABLE IF NOT EXISTS move_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    move_id     INTEGER NOT NULL REFERENCES moves(id),
    pv_rank     INTEGER NOT NULL,        -- 1 = best, 2 = second-best, 3 = third-best
    eval_cp     INTEGER,
    eval_mate   INTEGER,
    move_san    TEXT,
    pv_json     TEXT,
    nodes       INTEGER,
    UNIQUE(move_id, pv_rank)
);
CREATE INDEX IF NOT EXISTS idx_move_lines_move ON move_lines(move_id);

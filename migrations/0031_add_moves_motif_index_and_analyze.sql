-- Partial index for tactical-motif queries (get_motif_drill_positions,
-- get_motif_breakdown): only ~1.2k of the 2.3M moves rows carry a motif
-- label, so a partial index is tiny and turns those full-table scans
-- (~0.7-0.8s measured on the real 32k-game database) into ~4-10ms seeks.
CREATE INDEX IF NOT EXISTS idx_moves_motif ON moves(motif) WHERE motif IS NOT NULL;

-- First-ever ANALYZE for this database (verified: no sqlite_stat1 existed
-- before this migration). Without real statistics SQLite's planner kept
-- preferring the huge idx_moves_is_player_move over the tiny partial index
-- above (confirmed via EXPLAIN QUERY PLAN before/after on a copy of the
-- real database); a limited ANALYZE (analysis_limit=1000) was tried first
-- and was NOT sufficient to flip that choice -- only full statistics were.
-- One-time cost ~2.7s on the 1GB database; key existing plans
-- (idx_moves_player_cpl, idx_moves_game, idx_moves_fen_before,
-- idx_moves_zobrist, idx_moves_awaiting_annotation) verified unchanged
-- after stats exist.
ANALYZE;

-- Insurance fields: cheap to capture during the Phase 2 engine pass,
-- expensive (a full re-run) to backfill afterward.

-- Provenance: lets you safely mix/compare runs later (e.g. if you ever
-- re-analyze a subset at a different depth or after a Stockfish upgrade,
-- you can tell which rows came from which run instead of silently
-- averaging incompatible evals together).
ALTER TABLE moves ADD COLUMN engine_depth INTEGER;
ALTER TABLE moves ADD COLUMN engine_version TEXT;

-- Free byproduct of the same search that already produces eval_cp/best_move_san.
-- Capturing the full principal variation (not just the first best move) and
-- node count costs nothing extra at analysis time, but enables future metrics
-- you haven't thought of yet (e.g. "how often did the played continuation
-- diverge from the engine's planned line two moves later").
ALTER TABLE moves ADD COLUMN nodes INTEGER;
ALTER TABLE moves ADD COLUMN pv_json TEXT;   -- JSON list of SAN moves in engine's principal variation

-- Position before the move, in FEN. Not produced by the engine search itself,
-- but cheap to store (~70 bytes/row) and removes the need to ever replay the
-- SAN move sequence again for some future static-position feature
-- (material balance, piece activity, pawn structure, etc.) — pure backfill
-- convenience, computed once from data already in this table.
ALTER TABLE moves ADD COLUMN fen_before TEXT;

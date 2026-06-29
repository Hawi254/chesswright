-- Tactical motif label for mistake/blunder moves: fork, pin, skewer,
-- discovery, back_rank_mate, hanging. Populated by annotate.py Pass 4
-- (classify_motif in motif.py) using python-chess pattern detection on
-- fen_before + best_move_san. NULL on non-blunder moves and on any move
-- where fen_before or best_move_san is missing.
ALTER TABLE moves ADD COLUMN motif TEXT;

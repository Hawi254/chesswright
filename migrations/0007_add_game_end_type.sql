-- Derivable purely from the final board position after replaying the move
-- sequence -- no engine, no PGN re-read. Termination only gives coarse
-- buckets (Normal/Time forfeit/Abandoned); this distinguishes what
-- actually happened at the end of a "Normal" game.
ALTER TABLE games ADD COLUMN game_end_type TEXT;
-- one of: checkmate, stalemate, insufficient_material, draw_repetition,
-- draw_50_move_rule, draw_agreement, resignation, time_forfeit, abandoned, unknown

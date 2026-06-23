-- Phase 3-style recompute (annotate.py), same category as is_puzzle_trigger/
-- puzzle_sequence_length: best-move streaks -- the player matching the
-- engine's literal top move (san=best_move_san) for 3+ consecutive own
-- turns, anchored at the streak's first ply (one row per streak, not one
-- row per ply within it -- same convention puzzle_sequence_length uses).
--
-- A streak only qualifies (is_best_move_streak_trigger=1) if its FIRST
-- move was itself "unforced" (competitive margin -- the existing
-- move_lines rank1-vs-rank2 gap stored in moves.sharpness, read inverted
-- here: small gap = several moves were genuinely close in quality, so
-- finding the best one was a real choice, not just the only sensible
-- move). This means every qualifying row already has
-- best_move_streak_unforced_count >= 1 by construction -- the column
-- still matters because later moves in the streak can be forced or
-- unforced too, and "every move was a real choice" is a stronger signal
-- than "just the first one was."
--
-- NULL = not yet computed (opponent plies, or own plies not yet
-- analyzed); 0 = computed, doesn't qualify -- same NULL-vs-0 convention
-- already used for is_brilliant_candidate.
ALTER TABLE moves ADD COLUMN best_move_streak_length INTEGER;
ALTER TABLE moves ADD COLUMN is_best_move_streak_trigger INTEGER;
ALTER TABLE moves ADD COLUMN best_move_streak_unforced_count INTEGER;

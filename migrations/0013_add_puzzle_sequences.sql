-- Phase 4b slice 3: puzzle-candidate sequence detection. A trigger ply T
-- is a mistake/blunder by mover M; puzzle_sequence_length counts how many
-- of the opponent O's immediately following plies (T+1, T+3, ...) were
-- played accurately in a row, before the first gap/non-qualifying move/
-- game end. is_puzzle_trigger=1 only when T itself qualifies AND the
-- follow-up streak clears the configured minimum length. Computed in
-- annotate.py (pure recompute over already-stored classifications, same
-- pattern as is_brilliant_candidate -- no new engine search needed).
ALTER TABLE moves ADD COLUMN is_puzzle_trigger INTEGER;
ALTER TABLE moves ADD COLUMN puzzle_sequence_length INTEGER;

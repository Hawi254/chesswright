-- Phase 3b: sharpness (rank1-vs-rank2 move_lines eval gap, "how forced was
-- the best move") and material_delta (mover's material gain this ply, from
-- captures/promotions -- always >= 0 by construction; a *sacrifice* shows
-- up as the OPPONENT's next-ply material_delta being large, not this one's)
-- feed a conservative "brilliant move candidate" flag for Phase 4 review.
--
-- material_delta: ingest.py (tier 2 -- derivable from board+move alone, no
-- engine). sharpness / is_brilliant_candidate: annotate.py (recomputable
-- post-processing over move_lines + cpl/classification, same pattern as
-- Phase 3a -- no new engine search needed).
ALTER TABLE moves ADD COLUMN material_delta INTEGER;
ALTER TABLE moves ADD COLUMN sharpness INTEGER;
ALTER TABLE moves ADD COLUMN is_brilliant_candidate INTEGER;

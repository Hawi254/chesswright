-- Performance fix for the Analysis Jobs view's "K games awaiting
-- annotation" notification (annotate.count_games_awaiting_annotation()):
-- that query filters directly on moves.cpl/eval_cp/eval_mate, none of
-- which had an index, forcing a full scan of `moves` on every poll (the
-- Analysis Jobs page polls it every 2s, the app.py sidebar every 5s, on
-- EVERY page). Invisible on a small database, but measured directly
-- against a synthetic ~32k-game/2.76M-move database (matching the
-- original chess-analyzer project's real scale, BRIEF.md) at ~753ms per
-- call -- a recurring cost for as long as the app is open, not a
-- one-time charge.
--
-- A partial index matching the query's actual predicate (not a plain
-- index on cpl alone, which would still have to scan every "done" row
-- to filter eval_cp/eval_mate) turns the plan from "SCAN m" into an
-- index scan -- measured 3.4x faster (753ms -> 224ms) even against a
-- deliberately exaggerated worst case (389k matching rows, closer to a
-- large db_import.py of a previously-analyzed-but-never-annotated
-- database than to normal steady-state usage, where annotate.py runs
-- promptly after each batch and this set stays small).
--
-- (game_id, ply) columns, not just a bare partial index with no columns:
-- this lets the same index also satisfy the query's join/ply comparison
-- without a second lookup back into the base table for those columns.
CREATE INDEX IF NOT EXISTS idx_moves_awaiting_annotation
ON moves(game_id, ply)
WHERE cpl IS NULL AND (eval_cp IS NOT NULL OR eval_mate IS NOT NULL);

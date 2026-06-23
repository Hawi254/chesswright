-- Almost every Phase 3/4 query needs "only the moves the player actually
-- played, not the opponent's" -- currently that means joining to games.player_color
-- every time. Denormalizing it onto moves directly (computed once, cheaply,
-- at ingest time) makes the single most common query in this whole project
-- a plain WHERE clause instead of a join.
ALTER TABLE moves ADD COLUMN is_player_move INTEGER;
CREATE INDEX IF NOT EXISTS idx_moves_is_player_move ON moves(is_player_move);

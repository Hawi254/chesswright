-- Missing indexes on the games table.
--
-- analytics.py's acpl_and_blunder_rate() and classify functions join
-- moves→games and filter/group by opening_family, time_control_category,
-- and player_color. Without indexes SQLite scans all 32k+ game rows for
-- each bucket in the N+1 query loops (get_phase_accuracy, get_openings_table,
-- get_acpl_by_time_control, etc.).
--
-- The analysis_status index covers the worker queue (with queue_order) but
-- also the frequent "WHERE analysis_status='done'" filter that nearly every
-- analytical query uses.

CREATE INDEX IF NOT EXISTS idx_games_opening_family
    ON games (opening_family);

CREATE INDEX IF NOT EXISTS idx_games_time_control
    ON games (time_control_category);

CREATE INDEX IF NOT EXISTS idx_games_player_color
    ON games (player_color);

-- Composite for the most common analytical filter pattern:
-- WHERE analysis_status='done' AND opening_family=?
CREATE INDEX IF NOT EXISTS idx_games_status_opening
    ON games (analysis_status, opening_family);

-- moves compound index for the analytics temp-table joins:
-- JOIN moves m ON m.game_id=g.id WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
-- The existing idx_moves_game(game_id, ply) covers ORDER BY; this covers the filter.
CREATE INDEX IF NOT EXISTS idx_moves_player_cpl
    ON moves (is_player_move, cpl)
    WHERE cpl IS NOT NULL;

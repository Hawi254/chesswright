-- Materialized caches for two more Openings & Repertoire panels, same
-- shape as opening_position_stats_cache (migration 0029) and same
-- underlying reason: get_most_repeated_positions and get_repertoire_holes
-- both ran a full GROUP BY over all of moves/games via duck_conn on every
-- distinct slider position -- and the expensive part (the GROUP BY
-- itself) never actually depended on the slider values (min_games/top_n,
-- min_appearances/top_n), only the HAVING/LIMIT applied on top of it did.
-- Every slider nudge was a fresh ~2-3s (holes) to ~9s+ (repeated
-- positions, unrestricted by ply unlike the opening cache) full scan for
-- no reason -- st.cache_data was keying on values that didn't change the
-- expensive computation at all.
--
-- Both tables bake in the loosest threshold any real caller ever uses
-- (confirmed by reading every call site, not assumed): min_games=5 for
-- repeated positions (the UI never exposes this as a slider, it's always
-- the default) and min_appearances=3 for holes (openings_view.py's own
-- slider floor -- drill_export_view.py/srs_drill_view.py always pass 5,
-- within that floor). Reading with a stricter threshold or a smaller
-- top_n is then just a cheap WHERE+ORDER BY+LIMIT over an already-small
-- cached table, instead of a live aggregation.
--
-- Rebuilt by analytics.ensure_repeated_positions_cache /
-- ensure_repertoire_holes_cache, same idempotent/persisted/count-sentinel
-- pattern as the other ensure_* functions, each with their own
-- ctx_cache_meta column (own filter criteria -- zobrist_hash IS NOT NULL
-- vs is_player_move=1 AND cpl IS NOT NULL -- so they can go stale
-- independently, matching how ensure_structure_ctx/ensure_session_ctx
-- already track separate counts despite frequently coinciding).
--
-- Measured build cost on the real ~2.3M-row moves table: repeated
-- positions ~30s (touches every ply, not just the opening phase --
-- "most-repeated" is a whole-game concept, unlike the opening tree),
-- holes ~9s (bounded by is_player_move=1 AND cpl IS NOT NULL, i.e. only
-- analyzed games -- a much smaller subset). Both are one-time costs paid
-- only when the underlying move data actually changes, not per click.

CREATE TABLE IF NOT EXISTS repeated_positions_cache (
    ply             INTEGER NOT NULL,
    zobrist_hash    INTEGER NOT NULL,
    n_games         INTEGER NOT NULL,
    win_pct         REAL NOT NULL,
    draw_pct        REAL NOT NULL,
    loss_pct        REAL NOT NULL,
    common_opening  TEXT,
    PRIMARY KEY (ply, zobrist_hash)
);

CREATE TABLE IF NOT EXISTS repertoire_holes_cache (
    fen_before          TEXT PRIMARY KEY,
    n_games             INTEGER NOT NULL,
    n_distinct_moves    INTEGER NOT NULL,
    avg_cpl             REAL,
    approx_move_number  INTEGER,
    hole_score          REAL,
    most_played_san     TEXT,
    opening             TEXT
);

ALTER TABLE ctx_cache_meta ADD COLUMN repeated_positions_move_count INTEGER;
ALTER TABLE ctx_cache_meta ADD COLUMN repertoire_holes_move_count INTEGER;

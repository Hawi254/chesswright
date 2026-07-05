-- Materialized aggregate cache for the Opening Tree explorer (Pro feature).
--
-- Migration 0028 made get_opening_moves_from_fen's per-click lookup an
-- index seek (idx_moves_fen_before) instead of a full table scan. Measured
-- afterward: the seek itself is fast, but the popular early positions (the
-- ones actually clicked most -- e.g. ~16k games reach the starting
-- position) still cost ~0.2s because the JOIN + GROUP BY + COUNT DISTINCT
-- aggregation runs live, over thousands of matched rows, on every click.
--
-- This table precomputes that aggregation once, for the whole opening
-- phase (ply <= 40, i.e. the first 20 full moves each side -- past that,
-- "opening tree" stops being a meaningful frame and branches thin out to
-- n_games=1 anyway, so caching them buys nothing and just bloats the
-- table). Keyed by (zobrist_hash, ply, player_color) rather than the FEN
-- string -- smaller index, and it merges transposed move orders that reach
-- the same position, the same position-identity convention
-- opening_explorer.py already established for this codebase's tree
-- concept (see its module docstring) and idx_moves_zobrist (migration
-- 0003) already supports.
--
-- Rebuilt by analytics.ensure_opening_position_stats() -- same
-- idempotent-per-connection, persisted, count-sentinel pattern as
-- structure_ctx_cache/session_ctx_cache (migration 0023); reuses that same
-- ctx_cache_meta sentinel row (new column) rather than inventing a
-- parallel one.
--
-- Measured on the 2.29M-row live moves table: ~5.6s to build + ~0.4s to
-- index, paid once (only when the underlying move count changed since the
-- last build) instead of ~0.2s on every single row click. Point lookups
-- against the built cache: ~0.02-0.1ms.

CREATE TABLE IF NOT EXISTS opening_position_stats_cache (
    ply            INTEGER NOT NULL,
    zobrist_hash   INTEGER NOT NULL,
    player_color   TEXT    NOT NULL,
    san            TEXT    NOT NULL,
    is_player_move INTEGER NOT NULL,
    n_games        INTEGER NOT NULL,
    n_wins         INTEGER NOT NULL,
    n_draws        INTEGER NOT NULL,
    n_losses       INTEGER NOT NULL,
    avg_cpl        REAL,
    PRIMARY KEY (zobrist_hash, ply, player_color, san)
);

ALTER TABLE ctx_cache_meta ADD COLUMN opening_stats_move_count INTEGER;

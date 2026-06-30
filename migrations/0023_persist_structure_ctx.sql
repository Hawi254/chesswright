-- Persistent cache for the structure and session context tables.
--
-- compute_structure_context() reads all 2.3M move rows into Python to
-- derive per-game middlegame/endgame material signatures. On 32k games
-- this costs ~11-12s every cold Streamlit server start (the connection is
-- @st.cache_resource so the TEMP TABLE survives page navigations, but not
-- app restarts). By caching the result in a permanent table we pay that
-- cost once -- on the first start after new games are ingested -- and
-- then load the 32k-row cache into the TEMP TABLE in <100ms on all
-- subsequent starts.
--
-- compute_session_context() (all 32k games, pure Python loop) costs ~500ms
-- cold and is persisted by the same mechanism.
--
-- Invalidation sentinel: a single-row meta table stores the game count at
-- build time. When the game count changes (new games ingested), the cache
-- is treated as stale and rebuilt. This handles the common case; edge cases
-- like game deletion are acceptable (rebuild is safe, just slow).

CREATE TABLE IF NOT EXISTS structure_ctx_cache (
    game_id      TEXT PRIMARY KEY,
    middlegame_sig TEXT,
    endgame_sig    TEXT,
    endgame_ply    INTEGER
);

CREATE TABLE IF NOT EXISTS session_ctx_cache (
    game_id            TEXT PRIMARY KEY,
    session_game_number INTEGER,
    prior_outcome       TEXT,
    losing_streak       INTEGER
);

-- Single sentinel row; rebuilt by ensure_*_ctx when stale.
CREATE TABLE IF NOT EXISTS ctx_cache_meta (
    id                      INTEGER PRIMARY KEY,
    structure_game_count    INTEGER,
    session_game_count      INTEGER,
    built_at                TEXT DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO ctx_cache_meta (id, structure_game_count, session_game_count)
VALUES (1, 0, 0);

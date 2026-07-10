-- Add session_start/session_end to session_ctx_cache -- the Playing
-- Sessions rollup (roadmap §15 unit #4, get_session_rollup in
-- dashboard/data/patterns.py) needs each game's session boundaries, not
-- just its position within the session (session_game_number) and the
-- prior game's outcome, which is all the existing columns capture.
--
-- Forces one rebuild: ensure_session_ctx's fast path (analytics.py) treats
-- session_ctx_cache as current purely by comparing games.COUNT(*) to
-- ctx_cache_meta.session_game_count. This migration doesn't add or remove
-- any games, so that count comparison alone would never trip -- an
-- existing cache built before this migration would keep looking "current"
-- forever, with NULL session_start/session_end silently persisting.
-- Setting the stored count to an impossible sentinel (-1) makes
-- ensure_session_ctx's `meta[0] == game_count` check fail unconditionally
-- on the very next call, forcing a real rebuild (compute_session_context)
-- regardless of the actual game count.
ALTER TABLE session_ctx_cache ADD COLUMN session_start TEXT;
ALTER TABLE session_ctx_cache ADD COLUMN session_end TEXT;

UPDATE ctx_cache_meta SET session_game_count = -1 WHERE id = 1;

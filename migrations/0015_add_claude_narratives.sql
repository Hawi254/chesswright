-- Persists on-demand Claude API commentary (per-game/opening/opponent) so
-- a generated response survives a rerun/restart instead of being thrown
-- away the moment the user navigates elsewhere. subject_key is the
-- game_id for 'game', "{opening_family}|{player_color}" for 'opening',
-- and opponent_name for 'opponent'. UNIQUE + INSERT OR REPLACE (same
-- idempotent-overwrite pattern ingest.py already uses) so "Regenerate"
-- cleanly replaces the prior response rather than accumulating history.
CREATE TABLE claude_narratives (
    id             INTEGER PRIMARY KEY,
    subject_type   TEXT NOT NULL CHECK(subject_type IN ('game', 'opening', 'opponent')),
    subject_key    TEXT NOT NULL,
    response_text  TEXT NOT NULL,
    model          TEXT NOT NULL,
    generated_at   TEXT NOT NULL,
    UNIQUE(subject_type, subject_key)
);

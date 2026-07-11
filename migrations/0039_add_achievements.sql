-- Achievements Service (docs/superpowers/specs/2026-07-11-achievements-service-design.md).
-- Permanent unlock record only -- binary unlocked/not-unlocked, no
-- progress-toward-next state (deliberately out of scope for v1).
CREATE TABLE achievements_unlocked (
    achievement_id  TEXT PRIMARY KEY,
    unlocked_at     TEXT NOT NULL,
    source_game_id  TEXT REFERENCES games(id)
);

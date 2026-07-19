-- Adds 'opponent_prep_notes' and 'tournament_prep' to
-- claude_narratives.subject_type's CHECK constraint, for the Opponent Prep
-- page's Scouting Notes (subject_key=opponent username, stored in the
-- opponent's own isolated DB) and Tournament Prep Report (same key shape,
-- also opponent-scoped) features.
-- Same rebuild pattern as migrations 0016/0017/0025 -- SQLite has no ALTER
-- TABLE ... MODIFY/DROP CONSTRAINT.
CREATE TABLE claude_narratives_new (
    id             INTEGER PRIMARY KEY,
    subject_type   TEXT NOT NULL CHECK(subject_type IN ('game', 'opening', 'opponent', 'findings', 'coaching', 'game_report', 'opponent_prep_notes', 'tournament_prep')),
    subject_key    TEXT NOT NULL,
    response_text  TEXT NOT NULL,
    model          TEXT NOT NULL,
    generated_at   TEXT NOT NULL,
    UNIQUE(subject_type, subject_key)
);

INSERT INTO claude_narratives_new (id, subject_type, subject_key, response_text, model, generated_at)
SELECT id, subject_type, subject_key, response_text, model, generated_at FROM claude_narratives;

DROP TABLE claude_narratives;
ALTER TABLE claude_narratives_new RENAME TO claude_narratives;

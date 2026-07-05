-- Adds 'game_report' to claude_narratives.subject_type's CHECK constraint.
-- Game reports (subject_type='game_report', subject_key=game_id) are a
-- Pro feature: a structured per-game coach's review (phase analysis,
-- annotated key moments, verdict) stored separately from the free narrative
-- (subject_type='game') so both can coexist for the same game under the
-- UNIQUE(subject_type, subject_key) constraint.
-- Same rebuild pattern as migrations 0016/0017 -- SQLite has no ALTER
-- TABLE ... MODIFY/DROP CONSTRAINT.
CREATE TABLE claude_narratives_new (
    id             INTEGER PRIMARY KEY,
    subject_type   TEXT NOT NULL CHECK(subject_type IN ('game', 'opening', 'opponent', 'findings', 'coaching', 'game_report')),
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

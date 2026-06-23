-- Adds 'findings' to claude_narratives.subject_type's CHECK constraint
-- (the Findings page's cross-finding synthesis). SQLite has no ALTER
-- TABLE ... MODIFY/DROP CONSTRAINT, so this rebuilds the table -- the
-- standard SQLite pattern: create the new shape, copy rows, drop the
-- old, rename. Existing game/opening/opponent rows are preserved.
CREATE TABLE claude_narratives_new (
    id             INTEGER PRIMARY KEY,
    subject_type   TEXT NOT NULL CHECK(subject_type IN ('game', 'opening', 'opponent', 'findings')),
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

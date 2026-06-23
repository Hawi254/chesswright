-- Adds 'coaching' to claude_narratives.subject_type's CHECK constraint
-- (the Findings page's "what to work on" advice, a separate button/output
-- from the cross-finding synthesis -- same content-hash subject_key as
-- the 'findings' row for the same FINDINGS.md content, but a distinct
-- subject_type so both rows coexist under the UNIQUE(subject_type,
-- subject_key) constraint). Same rebuild pattern as migration 0016 --
-- SQLite has no ALTER TABLE ... MODIFY/DROP CONSTRAINT.
CREATE TABLE claude_narratives_new (
    id             INTEGER PRIMARY KEY,
    subject_type   TEXT NOT NULL CHECK(subject_type IN ('game', 'opening', 'opponent', 'findings', 'coaching')),
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

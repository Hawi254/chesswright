-- One row per worker session. Lets you answer "which config analyzed
-- this move" forever after -- essential now that you've changed engine
-- config mid-project (adding multipv=3); without this link, mixing
-- single-line and multipv-3 evals into the same aggregate later would be
-- invisible and easy to get wrong.
CREATE TABLE IF NOT EXISTS analysis_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT,
    ended_at        TEXT,
    engine_version  TEXT,
    depth           INTEGER,
    multipv         INTEGER,
    threads         INTEGER,
    hash_mb         INTEGER,
    games_analyzed  INTEGER DEFAULT 0,
    plies_analyzed  INTEGER DEFAULT 0,
    notes           TEXT
);

ALTER TABLE moves ADD COLUMN analysis_run_id INTEGER REFERENCES analysis_runs(id);
CREATE INDEX IF NOT EXISTS idx_moves_run ON moves(analysis_run_id);

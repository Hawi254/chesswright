-- Historical snapshot store (docs/superpowers/specs/2026-07-14-insights-
-- page-redesign-phase2-snapshot-store-design.md). One row per calendar
-- day, upserted by snapshots.record_snapshot() on every sync. Mirrors
-- get_headline_stats()'s exact field set so Unit 3's trend indicators
-- diff "now" (always live) against a specific past row here.
CREATE TABLE metric_snapshots (
    snapshot_date       TEXT PRIMARY KEY,
    total_games         INTEGER NOT NULL,
    analyzed_games      INTEGER NOT NULL,
    acpl                REAL,
    blunder_rate        REAL,
    win_pct             REAL,
    n_analyzed_moves    INTEGER NOT NULL,
    implied_rating      INTEGER,
    rating_confidence   TEXT
);

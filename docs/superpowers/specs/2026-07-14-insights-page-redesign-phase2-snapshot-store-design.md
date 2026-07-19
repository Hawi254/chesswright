# Insights Page Redesign — Phase 2, Unit 2: Historical Snapshot Store

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/superpowers/specs/2026-07-14-insights-page-redesign-phase2-rating-
benchmark-design.md` (Unit 1, shipped) decomposed Phase 2 into five
sub-projects. This spec covers #2, historical snapshot store — pure
infrastructure, the prerequisite Unit 3 (trend indicators) needs. It has
no UI surface of its own.

Checked against the real codebase before scoping: every metric this app
shows is computed live, on every read, over full history —
`get_rating_trajectory` (yearly), `get_progress_by_month` (monthly),
`get_headline_stats` (`dashboard/data/_shared.py:206`, all-time). Nothing
persists a point-in-time value, so there is no way to answer "what was
my ACPL 90 days ago" without a stored series. `achievements.py` is the
one existing precedent for a durable, append-only table fed by a
pipeline hook (`sync.py`'s `achievements.evaluate(achievements_conn,
"sync")` at `sync.py:201`) rather than recomputed on read — this design
follows that precedent's shape closely.

**Real constraint found while scoping this**: `sync.py` has never
imported `duckdb` (confirmed by grep — zero `duckdb` references in the
file). `get_headline_stats()` needs both a `duck_conn` and a
`sqlite_conn`. Routing the snapshot write through
`connections.get_duckdb_connection()` would pull the hard-won per-PID
DuckDB-snapshot machinery (`connections.py`'s `_build_duck_snapshot` —
built for a long-running dashboard/API process, see the
`duckdb_sqlite_same_process_hazard` history in `connections.py`'s own
comments) into a short-lived CLI script invoked on every sync, adding a
full-database backup-API copy plus a `sqlite` extension load
(network-dependent unless bundled) to a hot path that doesn't need it.
Every field `get_headline_stats()` computes via `duck_conn` is a plain
`COUNT`/`SUM` over `games` that a raw `sqlite3` query answers identically
(DuckDB's `db.games` is the same SQLite table, just attached read-only
through a second engine) — so this design recomputes those fields
directly against `sqlite_conn` instead of reusing `get_headline_stats()`,
and never touches DuckDB from `sync.py`.

## Goals

- Persist one snapshot row per calendar day of the same headline metrics
  `get_headline_stats()` already exposes, so Unit 3 can diff "now" against
  "N days ago" without a live recompute of the past.
- Hook into the one place new data already reliably arrives (`sync.py`
  post-ingest) rather than adding a new background job or scheduler.
- Never let a snapshot failure break sync — same isolation
  `achievements.evaluate` already gets.
- Multiple syncs on the same day overwrite, not duplicate, that day's row.

## New module: `snapshots.py` (repo root)

Mirrors `achievements.py`'s placement and shape: a root-level module with
one write function called from `sync.py`, one read function called from
`api/main.py` — both taking a plain `sqlite3.Connection`, never a
`duck_conn`.

```python
"""Historical snapshot store for headline metrics (docs/superpowers/
specs/2026-07-14-insights-page-redesign-phase2-snapshot-store-design.md).
Sqlite-only by design -- see that spec's Context section for why this
deliberately does not reuse dashboard/data/_shared.py's
get_headline_stats(), which needs a duck_conn this module's only caller
(sync.py) has never opened and shouldn't have to.
"""
import datetime

import analytics
from confidence import confidence_tier, default_thresholds

# Duplicated from dashboard/data/_shared.py's MIN_ANALYZED_MOVES_FOR_
# RATING_BENCHMARK / estimate_rating_from_acpl rather than imported --
# same reasoning _shared.py itself already uses for its own local
# duplication of insights.py's MIN_BUCKET_MOVES: no root-level module
# imports from dashboard/data/ anywhere in this codebase today (confirmed
# by grep), and this module living at the repo root, called from sync.py,
# is not the place to introduce that new dependency direction.
MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING = 20


def _estimate_rating_from_acpl(acpl: float) -> int:
    """Identical formula to _shared.py's estimate_rating_from_acpl --
    see that function's docstring for the citation. Duplicated, not
    imported; see this module's docstring."""
    import math
    return round(3100 * math.exp(-0.01 * acpl))


def record_snapshot(conn):
    """Computes today's headline stats via plain sqlite3 queries (no
    duck_conn -- see module docstring) and upserts one row into
    metric_snapshots keyed on today's date. Called from sync.py right
    after achievements.evaluate(), wrapped in the same try/except
    isolation so a snapshot failure can never fail a sync."""
    today = datetime.date.today().isoformat()
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    analyzed_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE analysis_status='done'").fetchone()[0]
    n_moves, _, acpl, blunder_rate = analytics.acpl_and_blunder_rate(conn)
    win_row = conn.execute("""
        SELECT 100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*)
        FROM games WHERE outcome_for_player IS NOT NULL
    """).fetchone()
    win_pct = win_row[0] if win_row else None

    rating_confidence = None
    implied_rating = None
    if acpl is not None:
        rating_confidence = confidence_tier(
            n_moves, default_thresholds(MIN_ANALYZED_MOVES_FOR_SNAPSHOT_RATING))
        if rating_confidence != "insufficient":
            implied_rating = _estimate_rating_from_acpl(acpl)
        else:
            rating_confidence = None

    conn.execute("""
        INSERT INTO metric_snapshots
            (snapshot_date, total_games, analyzed_games, acpl, blunder_rate,
             win_pct, n_analyzed_moves, implied_rating, rating_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_date) DO UPDATE SET
            total_games=excluded.total_games, analyzed_games=excluded.analyzed_games,
            acpl=excluded.acpl, blunder_rate=excluded.blunder_rate,
            win_pct=excluded.win_pct, n_analyzed_moves=excluded.n_analyzed_moves,
            implied_rating=excluded.implied_rating,
            rating_confidence=excluded.rating_confidence
    """, (today, total_games, analyzed_games, acpl, blunder_rate, win_pct,
          n_moves, implied_rating, rating_confidence))
    conn.commit()
```

`sync.py` changes (immediately after the existing `achievements.evaluate`
block at `sync.py:191-206`): open one more short-lived connection (or
reuse `achievements_conn` — same file, no reason for a second handle),
call `snapshots.record_snapshot(achievements_conn)` inside the same
try/except, log-and-continue on failure:

```python
    try:
        achievements_conn = get_connection(db_path)
        achievements.evaluate(achievements_conn, "sync")
        snapshots.record_snapshot(achievements_conn)
    except Exception as e:
        print(f"WARNING: achievement evaluation failed (sync unaffected): {e}")
```

(The existing warning message becomes misleading once it also covers
snapshotting — rename to something like `"post-sync bookkeeping failed"`
as part of this change.)

## Schema: `migrations/0041_add_metric_snapshots.sql`

```sql
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
```

No index beyond the primary key — Unit 3's query pattern is a single
`ORDER BY snapshot_date DESC LIMIT 1` with a `WHERE snapshot_date <= ?`
range filter, which the primary key's implicit B-tree already serves; row
count is bounded by real-world days-since-install (low thousands at
most), not a scale that needs a secondary index.

## Non-goals

- No API endpoint in this unit — `metric_snapshots` has no consumer until
  Unit 3 reads it. Adding a raw "list snapshots" endpoint with no UI
  behind it would be exactly the kind of speculative surface this
  project's roadmap has repeatedly declined to build ahead of a real
  caller (see the Achievements Service precedent).
- No backfill of historical snapshots for rows that predate this
  migration — a fresh install (or an existing install right after this
  ships) starts with zero snapshot history and Unit 3 gates on that
  honestly (its own spec's job, not this one's).
- No snapshot on the `worker.py` "analysis" trigger (`worker.py:651`).
  Analysis completing between two syncs changes ACPL, but today's
  snapshot row (if one already exists) is not re-taken until the next
  sync — an accepted staleness window, not a bug, consistent with "sync"
  already being this app's one "new data has arrived" signal for
  achievements too.
- No changes to `get_headline_stats()` or any existing endpoint — this
  unit is additive only.

## Testing

- `tests/unit/test_snapshots.py` (new, `@pytest.mark.unit` where
  possible): `_estimate_rating_from_acpl` formula spot-check (mirrors
  `test_shared.py`'s existing test for the same formula).
- `tests/integration/test_snapshots.py` (new, DB-backed, mirrors
  `tests/integration/test_achievements.py`'s shape): `record_snapshot`
  against a seeded sqlite fixture — verifies the inserted row's fields
  match hand-computed expected values; verifies a second call on the same
  day upserts (row count stays 1, values update) rather than inserting a
  duplicate; verifies `acpl IS NULL` / `rating_confidence IS NULL` /
  `implied_rating IS NULL` when there are zero analyzed moves.
- `tests/integration/test_sync.py` (existing file — confirm at
  implementation time): extend for the new `snapshots.record_snapshot`
  call landing in the same try/except as `achievements.evaluate`, and
  that a `record_snapshot` exception doesn't propagate out of `sync.py`'s
  main flow.
- Live verification (`verify-live-dashboard` skill, since this only
  touches the sync pipeline, not the React/FastAPI surface): run a real
  sync against the worktree's dev `chess.db`, confirm one new row lands
  in `metric_snapshots` with today's date and sane values, confirm a
  second sync the same day doesn't add a second row.

## Open items for the implementation plan to resolve

- Exact wording of the renamed sync.py warning message.
- Whether `record_snapshot` should log at all on success (the rest of
  `sync.py`'s post-sync block is silent on success) — default to silent,
  confirm at implementation time against the surrounding code's voice.

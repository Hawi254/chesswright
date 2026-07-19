# Achievements Service — Design

Status: approved, not yet implemented
Date: 2026-07-11
Branch: feature/eval-dedup-cache

## Context

The Achievements Service has appeared in this project's roadmap
(`docs/implementation_roadmap.md` §7/§8/§12/§17/§21) as a shared
backend service meant to eventually feed three UI surfaces (Overview
Highlights carousel, Insights badges, Training Center). It has been
deliberately deferred three separate times, each time for the same
stated reason: "confirmed a real, clean gap, but building it now is
speculative — zero real callers exist yet."

This design is a deliberate, explicit exception to that "wait for a
first real consumer" rule, made by direct user request rather than
because a consumer surfaced. To keep that exception bounded, this
design is **backend only**: a schema, an evaluation engine, and a seed
catalog of concrete achievements grounded in data the app already
computes. No UI is built as part of this design. A future consumer
(whichever of the three surfaces gets picked up first) reads the
`achievements_unlocked` table directly; it does not need this service
to change shape to do so.

## Goals

- A durable, permanent record of which achievements a player has
  unlocked, and when.
- Evaluation that runs automatically as new qualifying data enters the
  database (new games via sync, new engine analysis via the worker),
  with no polling and no new background job.
- A seed catalog of ~12 concrete achievements, each grounded in a
  query or computed value that already exists elsewhere in the
  codebase — not invented signals.
- Safe to ship with zero consumers: evaluation must never be able to
  break the sync or analysis pipelines it hooks into.

## Non-goals (explicit)

- No UI: no carousel, no badge chips, no Training Center surface. This
  is the same "don't build the surface before it's asked for" judgment
  the roadmap has already applied to Achievements three times; this
  design only removes the "no data model exists yet" half of that
  blocker, not the "no UI exists yet" half.
- No progress-toward-next state (e.g. "7/10 games toward this streak").
  V1 is unlocked/not-unlocked only. Progress tracking needs running
  counters per in-progress achievement and adds real complexity with no
  consumer requesting it.
- No notifications. Desktop notifications for achievement unlocks are
  the separate Notification Service gap (`§7`), not part of this
  design.
- No Pro-gating decision. Whether a given achievement or achievement
  surface is free or Pro-gated is a per-consumer decision made when a
  real UI surface picks specific achievements to show, not something
  this backend-only design needs to resolve.
- No declarative rules DSL / config-editable criteria. See Architecture
  below for why.

## Architecture

**Approach: a Python registry of achievement definitions, evaluated by
one engine, triggered by direct calls from the two existing pipelines
that can produce qualifying data.**

Two alternatives were considered and rejected:

1. **Declarative YAML/operator rules engine** (achievements defined as
   `metric >= threshold` config, interpreted generically). Rejected:
   this project's achievement criteria are genuinely heterogeneous —
   consecutive-game streaks, one-time board-derived events (giant
   killing, comeback), calendar-day streaks, and count thresholds all
   need different evaluation shapes. Forcing them through one
   declarative operator model to make them "config-editable" is
   premature abstraction with no second author (human, non-Claude) who
   would benefit from editing achievements without touching Python.
2. **Event-sourced achievement log** (pipelines emit domain events to a
   log table; evaluators subscribe and process it). Rejected: this is
   a single-user desktop app with exactly two producers of qualifying
   data (sync, analysis). A message-bus/event-log architecture is the
   kind of "enterprise apparatus" this project's own Testing &
   Quality Strategy (`§9`) already decided to defer — direct function
   calls after `sync.run()` / `worker.run()` finish are sufficient.

**Module placement**: new `achievements.py` at the repo root, sibling
to `analytics.py`, `db.py`, `config.py`. It lives at the root (not in
`dashboard/data/`) because it is invoked from pipelines (`sync.py`,
`worker.py` / `dashboard/job_runner.py`), not just read by dashboard
pages — the same placement logic that already puts `analytics.py` at
the root rather than inside `dashboard/`.

Each achievement definition is a small Python object with:

- `id` — stable string identifier, primary key of the unlock table.
- `name`, `description` — display strings (unused by any UI yet, but
  needed so a future consumer doesn't have to invent copy from scratch).
- `category` — free-form tag (`streak` / `milestone` / `skill` /
  `narrative`) for future UI grouping. Not used for dispatch.
- `triggers` — subset of `{"sync", "analysis"}`: which pipeline
  completions could possibly newly satisfy this achievement. Used to
  skip irrelevant checks on a given trigger (e.g. a giant-killing
  achievement, which needs engine analysis, is never re-checked on a
  bare sync).
- `check(conn) -> game_id | True | None` — returns a truthy value
  (optionally a `game_id` string) if the achievement is now satisfied,
  `None` otherwise. Given a `sqlite_conn` for point lookups or
  `duck_conn` for aggregations, per this project's existing dual-
  connection convention.

## Data model

One new migration, `migrations/0039_add_achievements.sql`:

```sql
CREATE TABLE achievements_unlocked (
    achievement_id  TEXT PRIMARY KEY,
    unlocked_at     TIMESTAMP NOT NULL,
    source_game_id  TEXT NULL REFERENCES games(id)
);
```

- `achievement_id` is the catalog entry's `id`; primary key enforces
  the binary/permanent semantics (an achievement unlocks once, ever,
  and is never re-evaluated or revoked once present).
- `source_game_id` is nullable and lets a future UI deep-link "the
  game that earned this" for game-triggered achievements (giant
  killing, comeback, blunder-free game, swindle, marathon game).
  Milestone/streak achievements that aren't tied to one specific game
  leave it `NULL`.
- No catalog table. The catalog is plain Python data (same pattern as
  `dashboard/theme.py`'s `BADGE_CHIPS` dict), not user-editable, so it
  does not need to live in the database. This also means adding or
  editing achievements later is a code change, not a migration.
- No progress-tracking columns, per the stated non-goal.

## Seed catalog

Twelve achievements, each grounded in a query or computed value that
already exists in the codebase today — nothing invented for this
design:

| id | category | grounded in |
|---|---|---|
| `first_win` | milestone | `games` table, first `result='win'` row |
| `century_club` | milestone | 100 games with `analysis_status='done'` |
| `win_streak_10` | streak | consecutive wins ordered by date |
| `giant_killer` | narrative | `dashboard/data/game_explorer.get_game_badges` → first `is_giant_killing` |
| `comeback_kid` | narrative | same function → first `is_comeback` |
| `blunder_free_game` | skill | a fully-analyzed game with zero blunder-classified moves |
| `marathon_game` | milestone | a completed game with `num_plies` ≥ a config threshold |
| `opening_explorer` | milestone | `dashboard/data/openings.py` repertoire query, N distinct openings played |
| `swindle_artist` | narrative | reuses `points.py`'s `win_prob_before` curve + `LOST_WP` constant; new inverse derivation, not a copy of an existing boolean (see caveat below) |
| `session_warrior` | milestone | `session_ctx_cache` (Playing Sessions work), a session with ≥10 games |
| `consistency_streak` | streak | N consecutive calendar days with ≥1 game played |
| `drill_streak` | skill | `dashboard/data/srs.py` / `drills.py` existing review-streak state |

Exact list and thresholds are cheap to change later since the catalog
is plain Python, not a schema commitment — this is a starting set
sized to exercise the engine's different `check()` shapes (one-time
event, streak, calendar streak, count threshold), not a claim that
these are the "right" 12 achievements for an eventual UI.

**Grounding caveat, `swindle_artist`**: ten of these twelve reuse an
existing boolean or query outright (e.g. `giant_killer`/`comeback_kid`
read `get_game_badges`'s columns directly). `swindle_artist` is the one
exception — this codebase's existing "swindle" concept
(`points.py`'s `missed_swindle` bucket, `matchups.get_opponent_swindle_
rate`) is loss-side only: it tracks losses where the player *failed* to
convert a real comeback chance, not wins recovered from a lost
position. `swindle_artist`'s `check()` is new logic (player's
`win_prob_before` drops to `LOST_WP` or below at some point, then the
game result is a win) that reuses the same underlying win-probability
data and the same `LOST_WP` threshold constant, not an existing
per-game boolean. Flagged here so implementation doesn't assume a
one-line reuse where a small new classification is actually needed.

## Evaluation engine

`achievements.evaluate(conn, trigger)`:

1. For every catalog entry **not already present** in
   `achievements_unlocked`, whose `triggers` set includes the given
   `trigger`:
2. Call `check(conn)`.
3. If truthy, insert `(achievement_id, unlocked_at=now, source_game_id)`
   into `achievements_unlocked`.

Because already-unlocked achievements are skipped entirely and unlocks
are permanent, the amount of work done per call shrinks over time —
this stays cheap even called on every sync, with no caching layer
needed.

**Trigger hook points** (the two places in the codebase where
qualifying data actually enters the database):

- End of `sync.run()` (`sync.py`) → `achievements.evaluate(conn, "sync")`.
- End of `worker.run()` (`worker.py`), reached via
  `dashboard/job_runner.py`'s batch-completion path →
  `achievements.evaluate(conn, "analysis")`.

**Backfill script**: `backfill_achievements.py` at the repo root, same
precedent as `backfill_legal_reply_count.py` and
`backfill_batch_eval_cache.py`. Calls `evaluate(conn, trigger=None)`
(no trigger filter — checks every catalog entry regardless of
`triggers`) to sweep the full catalog against existing history once.
This means achievements already earned by past games unlock
immediately when the service is deployed, rather than only reacting to
games synced or analyzed after this ships.

## Error handling

Achievement evaluation runs as a best-effort post-step. Each pipeline
call site wraps its `evaluate()` call in a try/except that logs and
swallows any exception — a bug in one achievement's `check()` function
must never abort or fail the sync or analysis pipeline it's attached
to. Within `evaluate()` itself, one failing `check()` call is caught,
logged, and skipped so it doesn't prevent the remaining catalog entries
from being evaluated in the same pass.

## Testing

- Unit tests per seed achievement's `check()` function against
  hand-seeded fixtures, mirroring this project's existing
  `TestPatternsData` / `TestGameEndingsData` style in
  `tests/integration/test_data_layer.py`.
- One integration test covering the full trigger → `evaluate()` →
  unlock-row-inserted path, including the "already unlocked, not
  re-checked" case.
- One integration test for the backfill script's idempotency (running
  it twice inserts no duplicate rows), matching the pattern already
  established by `backfill_legal_reply_count.py`'s and
  `backfill_batch_eval_cache.py`'s own tests.
- Manual verification: since there is no UI to screenshot, run the
  backfill script once against a copy of the real dev `chess.db` and
  sanity-check which of the 12 seed achievements fire and how many —
  the same "actually run against real data" discipline this project
  already applies to its other backfill scripts.

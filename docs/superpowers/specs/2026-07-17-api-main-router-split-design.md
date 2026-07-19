# api/main.py Router Split — Design

Status: design approved by user, pending spec review
Branch: worktree-frontend-spike

## Context

`api/main.py` is 2,180 lines: every FastAPI route for every page (Overview,
Openings, Opening Tree, Evolution, Insights, Ask, Matchups, Patterns,
Variations, Annotations, Board Chat, Analysis Jobs, Opponent Prep,
Settings, plus SPA/static asset serving) lives in one file, alongside a
hand-written `_TTLCache` class (23 separate instances), ~10 Pydantic
request models, and JSON-serialization helpers. It is pure routing —
imports `dashboard/data/*.py` and calls existing functions, no duplicated
business logic — but it grows every time the `port-view-slice` skill
lands a new page's backend, and is now the largest source file in the
project outside tests.

`frontend/src/lib/charts.ts` (739 lines) was also surveyed but is a flat
library of ~14 independent, self-contained chart-builder functions —
lower urgency, out of scope for this design.

Streamlit-side files (`dashboard/patterns_view.py`, `settings_view.py`,
etc.) were also surveyed and excluded: per
[[streamlit_frontend_dropped_2026-07-13]], the Streamlit dashboard is
being retired entirely, so refactoring it for long-term maintainability
is low-value.

## Goal

Split `api/main.py` into one `APIRouter` module per page/feature area,
so future page work lands in one small file instead of appending to the
monolith, **with zero changes to the file's external contract** — every
integration test (~25 files) does `import api.main as api_main`, then
uses `api_main.app`, `api_main.reset_caches()`, and (one file)
`api_main.FRONTEND_DIST_DIR`. Grepped confirmation: nothing else is
reached into from outside `api/main.py`. All three must keep working
exactly as today.

## Constraints confirmed by inspection

- **PyInstaller bundling**: `chesswright-react.spec` bundles the whole
  `api/` directory as `datas` (`datas += [(str(ROOT / "api"), "api")]`),
  not a fixed file list — new files under `api/routers/` are picked up
  automatically, no spec changes needed.
- **Static/SPA serving stays in `main.py` itself.** `test_api_static.py`
  monkeypatches `api_main.FRONTEND_DIST_DIR` directly by attribute; moving
  asset-serving into a router would require also updating that test for
  no benefit, so `/assets/{path}`, the SPA fallback route, and the
  `FRONTEND_DIST_DIR` constant all remain on `main.py`.
- **No registry needed for cache reset.** `main.py` already has to import
  every router module to call `include_router()`, so it already "knows
  about" all of them — `reset_caches()` just calls each router's own
  `reset_caches()` explicitly. A cache registry would be an abstraction
  with no consumer.

## Performance finding folded into this design

While tracing call sites for the split, found that
`data.get_headline_stats(duck_conn, sqlite_conn)` — a full `moves JOIN
games` aggregate scan (`analytics.acpl_and_blunder_rate`, plus two more
DuckDB scalar queries) — is called at **9 separate sites** in
`api/main.py`, with **no cache of its own**, unlike the 23 other
comparably-expensive computations in the file. Two of those sites
(`/api/overview/headline-stats`, `/api/overview/headline-trend`) are
called directly and uncached on every Overview page load; two more
(`career_findings`, `narrative`) each wrap their *own* separate call to
it in their *own* `_TTLCache`, meaning a single Overview page visit (which
fires these endpoints roughly concurrently) recomputes the same scan at
least 4 times instead of once. The remaining 5 sites (opening/insights/
opponent narrative-generation, points-summary empty-case) are lower
frequency but share the same gap.

FastAPI's own docs confirm `include_router()` has no per-request cost —
merging happens once at startup — so the router split itself is
performance-neutral; this caching gap is a real, independent finding, not
a mechanical side effect. It's folded into this design (not filed as a
separate follow-up) because fixing it means touching the exact code this
split is already moving.

## New file layout

```
api/
  main.py              # FastAPI() + CORS + include_router() x15 + static/SPA
                        # routes + FRONTEND_DIST_DIR + reset_caches()
  cache.py              # TTLCache class (moved from main.py, unchanged)
  serialization.py      # _json_safe (moved from main.py, unchanged)
  shared_data.py         # NEW: _headline_stats_cache + get_headline_stats_cached()
  routers/
    overview.py          # engine-status, win-rate, headline-stats, rating/acpl
                        # trajectory, rating-snapshot, headline-trend,
                        # current-streak, career-findings, achievements,
                        # narrative, career-highlight
    games.py             # games/explorer
    openings.py           # openings/table, narrative (+generate), repeated-
                        # positions, position-fen, repertoire-holes, ply-accuracy
    opening_tree.py        # moves, map, timeline, changes, jump, srs
    evolution.py          # summary, family-trend, family-acpl
    insights.py            # synthesis, coaching (+generate variants)
    ask.py                 # ask/stream
    matchups.py            # rating-form, opponent-narrative (+generate)
    patterns.py            # clock-time, turning-points, pieces, positions,
                        # game-context, comparisons, sessions (+ their
                        # _*_tendency_card helpers)
    variations.py          # create/update/delete/list variations, variation pgn
    annotations.py          # game + variation annotation get/put/ai-comment
    board_chat.py           # conversations, turns, feedback
    analysis_jobs.py        # status/start/stop/lock-clear/settings/annotate/backfill
    opponent_prep.py        # start/stop/status/list/report/notes/tournament-report
    settings.py             # pro-status, claude-key-status, nav/pages
```

Each router instantiates its own `TTLCache` instances (imported from
`api/cache.py`) for page-local caching, and its own `reset_caches()`
function where it actually caches something. Router modules that need
`get_headline_stats_cached()` import it from `api/shared_data.py`.

## Migration order

**Phase 0 — caching fix, no files split yet.** Entirely inside
`main.py`: extract `TTLCache` → `api/cache.py`, `_json_safe` →
`api/serialization.py`, add `api/shared_data.py` with
`_headline_stats_cache` + `get_headline_stats_cached()`, and repoint all
9 existing `data.get_headline_stats(...)` call sites at the cached
wrapper. Run the full test suite against this before touching any router
boundary — isolates the one real behavior change (caching) from the
purely mechanical change (file-splitting) that follows.

**Phase 1+ — mechanical, one router at a time,** smallest/most
self-contained first, full test suite run after each before moving to
the next (each step is independently safe to stop after, since `main.py`'s
public surface never changes):

1. `analysis_jobs` + `opponent_prep`
2. `board_chat`
3. `variations` + `annotations`
4. `games` + `openings` + `opening_tree`
5. `evolution`
6. `insights`
7. `ask`
8. `matchups`
9. `settings`
10. `patterns` (biggest)
11. `overview` (last — already touched in Phase 0, now a clean move)

## Testing

- Full existing test suite (~25 `tests/integration/test_api_*.py` files)
  must pass unchanged after every phase — no test file edits anticipated.
- After Phase 0: a new unit/integration test asserting
  `get_headline_stats_cached()` returns the same cached instance within
  the TTL window (i.e. only computes once across multiple calls),
  mirroring the existing pattern for `_career_findings_cache` etc.
- After the full split: confirm `api_main.reset_caches()` still clears
  every cache across every router (no cache silently orphaned during a
  move) — extend the existing reset-caches test if one exists, or add one.
- Live-verify with the `verify` skill after the split completes: launch
  both dev servers, exercise Overview/Openings/Patterns/Board Chat pages
  against the real dev `chess.db`, confirm no route regressions.

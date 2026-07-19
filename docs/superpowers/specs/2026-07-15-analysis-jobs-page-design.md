# Analysis Jobs Page — Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `analysis_jobs_view.py`
("Analysis Jobs") as ⛔ not started, with a specific caveat: "needs a
streaming/polling story on the React side (Streamlit's rerun-on-poll
model has no direct equivalent)." This is also the last unbuilt
*operational* page — start/stop live Stockfish batches, watch progress,
tune engine/batch settings, catch up on annotation — as opposed to the
read-only analytics pages ported so far.

Per this session's explicit direction, this is a **fresh design**, not a
port of `analysis_jobs_view.py`'s stacked-`st.form`/`st.fragment`
structure. The Streamlit source (401 lines) and `dashboard/job_runner.py`
/ `joblock.py` are read for business logic and requirements only, per the
standing "Streamlit is reference not blueprint" directive — every
underlying capability it has is kept, but the layout, real-time
mechanism, and interaction model are designed from scratch, informed by
web research on background-job monitoring UI patterns (queued-state
communication, real progress over spinners, calm KPI-strip layouts) done
during this session's brainstorm.

## Goals

- Full functional parity with the Streamlit page: start/stop a batch,
  live progress (games done, cache hit rate, estimated time saved, ETA),
  queue counts (waiting/analyzed/failed/awaiting-annotation), a
  cross-process lock warning (external `worker.py` runs) with a
  stale-lock clear action, engine/batch settings (depth, multiPV, max
  games, max duration, threads, hash), an annotation-catch-up action,
  and an eval-reuse cache backfill action.
- A real-time model that fits a single-user local desktop app, not a
  copy of Streamlit's `st.fragment(run_every=...)` rerun trick.
- A layout that keeps the controls (start/stop, status) permanently
  visible regardless of what else is on screen — the Streamlit version's
  whole premise is "leave this page and the run keeps going," so control
  visibility shouldn't require scrolling back to the top.

## Key decisions (from this session's brainstorm + web research)

1. **Command Center layout: a persistent two-column split**, not a
   single scrolling column and not the app's existing `Tabs` primitive.
   Left rail (~260px, fixed) holds status/start-stop/queue counts/
   settings-entry-point and never scrolls out of view; the right column
   holds live telemetry and maintenance actions. Chosen over a tabbed
   Run/Settings/Maintenance workspace (Option B, considered and shown to
   the user as a mockup) because this page's whole point is a control
   that must stay reachable *while* the user is looking at anything
   else on the page — putting Start/Stop behind a tab reintroduces the
   "scroll/switch back to find the button" problem this page exists to
   avoid. Also chosen over a single unified card grid (Option C) for the
   same reason — a grid has no fixed, always-visible region.
2. **Plain polling, ~2s interval, one bundled endpoint** — not Server-Sent
   Events. The current React app has zero streaming infrastructure (every
   other hook is a one-shot `fetch`); SSE would introduce a genuinely new
   pattern (first streaming endpoint, `EventSource` client primitive,
   reconnect/backoff handling) for a single-user local app where the
   latency/load advantage SSE has over polling doesn't apply — there's no
   scale or bandwidth concern on localhost. 2s matches the Streamlit
   fragment's own cadence.
3. **One bundled `GET /api/analysis-jobs/status` endpoint**, not five.
   `job_runner.get_state()`, `joblock.status()`, the queue counts query,
   `annotate.count_games_awaiting_annotation()`,
   `annotate.motif_backfill_needed()`, and
   `backfill_batch_eval_cache.count_pending_groups()` are all cheap and
   always needed together on every 2s tick — bundling means one polling
   loop and one hook instead of six, the same reasoning already used for
   `/api/matchups/rating-form` and `/api/patterns/summary`.
4. **Settings live in a slide-over drawer**, not inline in the rail and
   not a separate page. Keeps the rail compact (a tall inline form would
   push the queue counts and lock warning out of the visible fold) while
   keeping settings one click away without leaving the page — settings
   changes are read alongside a running/idle status the user needs to
   see at the same time (e.g. "why is Save disabled").
5. **Maintenance cards (annotation catch-up, eval-cache backfill) render
   only while idle**, both of them — a deliberate simplification over
   the Streamlit version, which hid the annotation section during a run
   but only *disabled* the backfill button. One consistent rule ("nothing
   maintenance-related shows while a batch owns the database") is easier
   to reason about than two different rules for two very similar actions,
   and both actions are cheap to defer a few minutes until the batch
   finishes.
6. **The "batch finished → see what changed" link ships inert** (rendered,
   not a live link) — `batch_impact_view.py` ("Batch Impact") is itself
   still ⛔ unported, so there is nothing to link to yet. Same precedent
   as Overview's career-highlight Game Detail link when Game Detail
   wasn't ported yet (`frontend_rewrite/overview_career_highlight`
   history). Re-activated once Batch Impact has a real route.
7. **Annotate/backfill stay blocking POSTs** with a client-side loading
   state, not an async job pattern. Matches every other write-triggering
   action already in this codebase (openings/insights/opponent narrative
   generation, Board Chat turns) — a local single-user app has no reason
   to build a second concurrency model for "this POST takes a few
   seconds."
8. **The cross-process lock warning and its "Clear stale lock" action are
   part of the same rail**, not a separate banner elsewhere in the app
   shell — `joblock.status()` already reports whether the PID it names is
   still alive, so the UI decision (warn vs. offer to clear) is identical
   to the Streamlit version's, just relocated.

## Backend: FastAPI endpoints (`api/main.py`)

New imports needed: `import job_runner` (resolves via the `dashboard/`
`PYTHONPATH` entry the dev/verify scripts already set, same as `import
data`), `import annotate`, `import backfill_batch_eval_cache`, `import
worker` (for `parse_duration`). `joblock` and `config` are already
imported.

```python
class SaveJobSettingsRequest(BaseModel):
    depth: int
    multipv: int
    max_games: int | None
    max_duration: str | None
    threads: int
    hash_mb: int


def _analysis_job_status_payload():
    """Bundles everything the rail + telemetry column need on one 2s
    poll tick -- mirrors analysis_jobs_view.py's own _render_status(),
    which already computes all of this together for the same reason."""
    sqlite_conn, _ = get_db_connections()
    cfg = config.load_config()
    state = job_runner.get_state()
    running = job_runner.is_running()
    lock_info = joblock.status()

    pending, done, failed = sqlite_conn.execute("""
        SELECT
            SUM(CASE WHEN analysis_status IN ('pending','in_progress') THEN 1 ELSE 0 END),
            SUM(CASE WHEN analysis_status = 'done' THEN 1 ELSE 0 END),
            SUM(CASE WHEN analysis_status = 'failed' THEN 1 ELSE 0 END)
        FROM games
    """).fetchone()
    queue = {
        "waiting": pending or 0, "analyzed": done or 0, "failed": failed or 0,
        "awaitingAnnotation": annotate.count_games_awaiting_annotation(sqlite_conn),
    }

    telemetry = None
    run = None
    if running:
        run = {"gamesDone": state.get("games_done", 0)}
        active = sqlite_conn.execute(
            "SELECT id, started_at FROM analysis_runs WHERE ended_at IS NULL "
            "ORDER BY id DESC LIMIT 1").fetchone()
        if active is not None:
            run_id, started_at = active
            run["runId"], run["startedAt"] = run_id, started_at
            reused, engine_n, avg_ms = sqlite_conn.execute("""
                SELECT SUM(CASE WHEN eval_source='reuse' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN eval_source='engine' THEN 1 ELSE 0 END),
                       AVG(CASE WHEN eval_source='engine' THEN search_time_ms END)
                FROM moves WHERE analysis_run_id=? AND ply <= ?
            """, (run_id, worker.REUSE_EVAL_MAX_PLY)).fetchone()
            reused, engine_n = reused or 0, engine_n or 0
            eligible = reused + engine_n
            telemetry = {
                "reuseEvalsOn": cfg["engine"].get("reuse_evals", True),
                "cacheHitRate": (reused / eligible) if eligible else None,
                "estTimeSavedSec": (reused * avg_ms / 1000) if (reused and avg_ms) else None,
                "eta": None,  # computed client-side from startedAt/gamesDone/queue.waiting
            }

    return {
        "status": state.get("status", "idle"),
        "runSeq": state.get("run_seq", 0),
        "completedRunId": state.get("completed_run_id"),
        "error": state.get("error"),
        "run": run,
        "queue": queue,
        "telemetry": telemetry,
        "lock": dataclasses.asdict(lock_info) if lock_info else None,
        "maintenance": {
            "annotationPending": queue["awaitingAnnotation"],
            "backfillPending": backfill_batch_eval_cache.count_pending_groups(sqlite_conn),
            "motifBackfillNeeded": annotate.motif_backfill_needed(sqlite_conn),
        },
    }


@app.get("/api/analysis-jobs/status")
def analysis_job_status():
    return _analysis_job_status_payload()


@app.post("/api/analysis-jobs/start")
def start_analysis_job():
    cfg = config.load_config()
    try:
        job_runner.start(
            resolve_db_path(), cfg["engine"]["depth"], cfg["engine"]["multipv"],
            cfg["engine"]["threads"], cfg["engine"]["hash_mb"], cfg["engine"]["pv_max_len"],
            cfg["engine"]["path"], cfg["worker"]["max_games"],
            worker.parse_duration(cfg["worker"]["max_duration"]),
            cfg["worker"]["consecutive_failure_limit"], cfg["worker"]["commit_every_n_moves"],
            backlog_quota=cfg["ingestion"]["backlog_quota"],
            backlog_quota_window=cfg["ingestion"]["backlog_quota_window"])
    except (RuntimeError, joblock.LockHeldError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


@app.post("/api/analysis-jobs/stop")
def stop_analysis_job():
    job_runner.stop()
    return {"ok": True}


@app.post("/api/analysis-jobs/lock/clear")
def clear_analysis_job_lock():
    joblock.force_release()
    return {"ok": True}


@app.get("/api/analysis-jobs/settings")
def get_analysis_job_settings():
    cfg = config.load_config()
    return {
        "depth": cfg["engine"]["depth"], "multipv": cfg["engine"]["multipv"],
        "threads": cfg["engine"]["threads"], "hashMb": cfg["engine"]["hash_mb"],
        "maxGames": cfg["worker"]["max_games"], "maxDuration": cfg["worker"]["max_duration"],
    }


@app.put("/api/analysis-jobs/settings")
def save_analysis_job_settings(body: SaveJobSettingsRequest):
    if job_runner.is_running():
        raise HTTPException(status_code=409, detail="Settings are read-only while a batch is running.")
    config.set_engine_setting("depth", body.depth)
    config.set_engine_setting("multipv", body.multipv)
    config.set_engine_setting("threads", body.threads)
    config.set_engine_setting("hash_mb", body.hash_mb)
    config.set_worker_setting("max_games", body.max_games)
    config.set_worker_setting("max_duration", body.max_duration)
    return {"ok": True}


@app.post("/api/analysis-jobs/annotate")
def run_annotation_pass():
    sqlite_conn, _ = get_db_connections()
    cfg = config.load_config()
    annotate.run(resolve_db_path(), cfg["annotation"]["mate_score_cap_cp"],
                  cfg["annotation"]["thresholds"], cfg["annotation"]["brilliant_material_threshold_cp"],
                  cfg["annotation"]["puzzle"], cfg["annotation"]["best_move_streak"], game_id=None)
    return {"ok": True}


@app.post("/api/analysis-jobs/backfill")
def run_cache_backfill():
    stats = backfill_batch_eval_cache.backfill(resolve_db_path())
    return {"insertedCount": stats.inserted, "groupsSeen": stats.groups_seen}
```

Notes:
- `resolve_db_path()` is `connections.resolve_db_path()`, already
  imported elsewhere in this style (`from connections import get_config`
  — add `resolve_db_path` to that same import line).
- ETA is computed client-side (not server-side, unlike the Streamlit
  version) because it's a pure function of three already-transmitted
  numbers (`queue.waiting`, `run.gamesDone`, `run.startedAt`) evaluated
  against the client's own clock tick — computing it server-side would
  just mean re-deriving `now()` on every poll for no benefit, and keeps
  `_analysis_job_status_payload()` a pure data bundle.
- `start`/`stop`/`lock/clear`/`annotate`/`backfill` are all uncached,
  side-effecting POSTs, matching every other write endpoint's style in
  this file (no `_TTLCache` involved).
- No new caching: `_analysis_job_status_payload()` intentionally isn't
  wrapped in a `_TTLCache` — a 2s poll of already-cheap queries needs no
  cache layer, and caching it would just add staleness to a value whose
  entire purpose is being current.

## Frontend

### Hook (`frontend/src/hooks/`)

- **`useAnalysisJobStatus()`** — the one polling hook this page needs.
  `setInterval(2000)` fetch of `/api/analysis-jobs/status` for the
  lifetime of the mounted component, cleared on unmount (same
  cancelled-on-unmount discipline every other hook already uses, just
  with an interval instead of a single fetch). Returns
  `{ data, loading, connectionLost }` — `connectionLost` flips true only
  after a poll tick fails, and the hook keeps serving the last-known
  `data` rather than clearing it, so a transient miss doesn't blank the
  rail. Client-side ETA derivation (`queue.waiting * (elapsedSince(run.startedAt) / run.gamesDone)`)
  lives here, not in a component, so every consumer of `data.telemetry`
  sees the same computed value.
- **`useAnalysisJobSettings()`** — plain get/save hook for the drawer,
  same `loading`/`error`/`saving`/`saveError`/`save()` shape as
  `useGameAnnotation`'s save flow. Independent of the polling hook — the
  drawer only needs to fetch once, on open.

### Components

- **`AnalysisJobsPage.tsx`** — composes `useAnalysisJobStatus()` and
  renders the two-column Command Center: `<ControlRail>` (fixed-width
  left) + `<TelemetryColumn>` (fluid right), plus the mounted-on-demand
  `<JobSettingsDrawer>`.
- **`ControlRail.tsx`** — status badge + elapsed time, primary
  Start/Stop button (label and handler keyed off `data.status`), the
  lock-warning card (only when `data.lock?.alive` or a clearable stale
  lock exists), the queue-count list, the settings-entry row (opens the
  drawer), and the CLI-hint caption. Owns the `start()`/`stop()`/
  `clearLock()` POST calls directly (no separate hook — three
  fire-and-refetch actions don't need their own state machine beyond a
  local `pending` flag per button).
- **`JobSettingsDrawer.tsx`** — slide-over panel, `useAnalysisJobSettings()`
  underneath. Depth/multiPV/max-games/max-duration up front, threads/hash
  under a disclosure (reuses the existing `accordion.tsx` primitive for
  that, rather than a bespoke collapsible). Read-only (all inputs
  disabled, Save hidden) whenever `data.status === 'running'`, passed in
  as a prop from `AnalysisJobsPage` rather than the drawer re-deriving it.
- **`RunTelemetry.tsx`** — the three cards (cache hit rate w/ bar, est.
  time saved, ETA), rendered only when `data.telemetry` is non-null.
  Cache-hit-rate card shows "Off" / "N/A" / a percentage per the same
  three-way logic the Streamlit version uses
  (`reuseEvalsOn` false / zero eligible plies / real ratio).
- **`MaintenanceCard.tsx`** — one small reusable card (headline text +
  action button + loading/error state), used twice: annotation catch-up
  (`maintenance.annotationPending || maintenance.motifBackfillNeeded`)
  and cache backfill (`maintenance.backfillPending > 0`). Both instances
  render only when `data.status !== 'running'`.
- **`BatchFinishedCard.tsx`** — small card shown when
  `data.status !== 'running' && data.completedRunId` is set and hasn't
  been dismissed this session (a `useState` flag in `AnalysisJobsPage`,
  the same run-seq-dedupe idea the Streamlit version uses via
  `st.session_state`, just as local component state instead). Renders
  "Batch #N finished" with an inert, non-interactive "See what changed"
  affordance (styled as disabled, not a working link) until Batch Impact
  exists as a real route.

### Page wiring (`App.tsx`)

`PAGE_COMPONENTS['analysis-jobs'] = AnalysisJobsPage` — `navCandidates.ts`
already has the `{ title: 'Analysis Jobs', url_path: 'analysis-jobs' }`
entry (currently falling back to `PageStub`). No new hidden route needed
— this page has no drill-down target.

## Non-goals

- Server-Sent Events or any other push mechanism (decision 2).
- A working Batch Impact link (decision 6) — `batch_impact_view.py` is
  unported; re-add once it exists.
- Any change to `dashboard/analysis_jobs_view.py`, `job_runner.py`,
  `joblock.py`, `annotate.py`, `backfill_batch_eval_cache.py`, or
  `worker.py` — all read-only inputs to this design, called as-is.
- An async/job-queue pattern for `annotate`/`backfill` (decision 7).
- Any settings beyond what the Streamlit form already exposes (no new
  engine/batch knobs invented for this pass).

## Testing

- `tests/integration/test_api_analysis_jobs.py` (new): `TestClient` +
  `migrated_db_path` fixture, monkeypatching `job_runner`/`joblock`
  module-level state directly (same technique `test_joblock.py` /
  `test_analysis_jobs_view.py` already use) rather than spinning up a
  real Stockfish batch in a unit test. Cover: idle/running/error/done
  status payload shapes, `start` success and both rejection paths
  (in-process already running → 409, `LockHeldError` → 409), `stop`,
  `lock/clear`, settings get/save (including the running → 409 guard),
  `annotate` and `backfill` happy paths.
- Hook tests: `useAnalysisJobStatus.test.ts` (interval-driven refetch via
  fake timers, `connectionLost` on a failed tick, recovery on the next
  successful one), `useAnalysisJobSettings.test.ts`.
- Component tests: `ControlRail.test.tsx` (all 5 states × lock-warning
  variants), `JobSettingsDrawer.test.tsx` (read-only while running,
  save/error), `RunTelemetry.test.tsx` (the 3-way cache-hit-rate logic),
  `MaintenanceCard.test.tsx`, `BatchFinishedCard.test.tsx` (inert link),
  `AnalysisJobsPage.test.tsx` (composition + running-hides-maintenance).
- Live verification (`verify` skill): start a real batch against the dev
  `chess.db`, confirm the rail updates every ~2s without navigating away
  and back, confirm Stop actually stops it, confirm the settings drawer
  is read-only mid-run, and confirm the maintenance cards disappear while
  running and reappear when it finishes (if pending counts are still
  nonzero).

## Open items for the implementation plan to resolve

- Exact fake-timer strategy for `useAnalysisJobStatus.test.ts` (Vitest's
  `vi.useFakeTimers()` vs. a manually-advanceable poll trigger) — decide
  at implementation time by checking what the existing hook test suite
  already standardizes on, if anything.
- Whether `ControlRail`'s three action buttons (start/stop/clear-lock)
  each own an independent `pending` flag or share one "an action is
  in-flight" flag that disables all three at once — resolve once the
  component is being written and the disabled-state UX can be checked
  against the actual poll cadence (a 2s-old `data.status` could
  otherwise let a user double-click Start before the first request's
  effect is visible).
- Confirm `analysis_runs.started_at` is stored as an ISO string parseable
  by `Date.parse` client-side for the ETA calculation (the Streamlit
  version parses it with `datetime.datetime.fromisoformat`) — verify the
  actual column format against the schema rather than assuming.

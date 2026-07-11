# Phase 6 — Settings Maturation — Design

Status: approved, not yet implemented
Date: 2026-07-11
Branch: feature/eval-dedup-cache

## Context

`docs/implementation_checklist.md` §6 (Phase 6 — Settings, Help &
Onboarding Maturation) confirms Settings is "entirely unstarted" beyond
the existing `settings_view.py`: 6 flat sections (API key, live engine,
DB import, Chess.com, Chesswright Pro, Support), no categorization, no
in-page search, no profiles/presets, no safeguards. Per the checklist's
own §10 recommended sequence, Phase 6 is "broad-but-shallow, lowest
engineering leverage" — picked up now by direct user request, not
because it moved up the priority order.

This design is scoped to **Settings only**. Help Center and Onboarding
Maturation (the other two items in Phase 6's table) are explicitly
deferred to a separate future session, per direct instruction. The
Notification Service item is also deferred — see Non-goals.

`config.yaml` (298 lines) has ~60 tunable parameters across 10 top-level
sections. Today only a handful have any UI at all: `interactive_engine`'s
6 fields (Settings' "Live engine settings"), and `engine.depth/multipv/
threads/hash_mb` + `worker.max_games/max_duration` (Analysis Jobs page,
not Settings — a deliberate existing split by where the setting is
*used*, which this design preserves rather than collapses). Everything
else is YAML-only today.

Two concrete, confirmed gaps motivated the specific scope below (not
invented — found by reading the actual call sites):

- `dashboard/live_engine.py:225` already tells the user *"Stockfish not
  found — configure the engine path in Settings"* — but no such control
  exists anywhere in Settings today. The app is making a promise it
  doesn't keep.
- `analytics.utc_offset_hours` is marked `CHANGE_ME` in `config.yaml`
  with no UI path to change it. Worse: the dashboard's own day×hour
  win-rate heatmap (`dashboard/data/patterns.py`) reads raw `hour_utc`
  and never applies this offset at all — only the older, separate CLI
  `analytics.py` report path does. The config key exists but the
  dashboard doesn't honor it yet.

## Goals

- Reorganize Settings into a tabbed category structure that scales to
  the settings this design adds, without turning into a 60-field wall.
- Close the two confirmed gaps above (engine location, timezone offset).
- Realize the roadmap's explicit call (§12 item 3): "Confidence/
  statistical-significance logic... one service, one set of thresholds,
  configurable once in Settings."
- Add a small, real "Engine Profiles" preset system, matching the
  roadmap's own named example (Laptop / Desktop / Deep Analysis /
  Tournament Mode).
- Add an in-Settings search/filter, distinct from the sidebar Global
  Search (which only navigates *to* the Settings page today).
- Add baseline safeguards (bounds, reset-to-default, confirm-before-delete)
  appropriate to a desktop app used by non-technical lichess players,
  not just the original developer.

## Non-goals (explicit)

- **Help Center, Onboarding Maturation** — separate future session, per
  instruction.
- **Notification Service** — deferred entirely. It needs its own
  delivery-mechanism design (system tray vs. in-app toast vs. OS-native)
  before a preferences UI would do anything real; building the toggle
  first would be a UI for a feature that doesn't exist. Tracked as a
  standing gap, not resolved here.
- **Any UI for `annotation.*` or `achievements.*`** — not even in the
  Advanced tier. Both bake into stored per-game data: `annotation.*`
  drives `moves.classification` at analysis time, `achievements.*`
  gates unlock fairness. Changing either post-hoc, for games already
  analyzed or achievements already evaluated, would silently desync
  history with no re-annotation/re-evaluation pass forcing consistency.
  This exclusion holds regardless of tier — it's a data-integrity
  boundary, not a UI-polish decision.
- **Collapsing the existing Analysis-Jobs/Settings split for batch
  engine settings.** `engine.depth/multipv/threads/hash_mb` and
  `worker.max_games/max_duration` stay on the Analysis Jobs page, where
  they're contextually used when starting a batch run. This design adds
  `engine.path` to Settings (identity-level config, not a per-run
  parameter) without duplicating the batch tuning fields there too.
- **Full N-way settings diffing/export/import.** Only the specific
  Engine Profiles snapshot described below — not a general
  export-all-settings-to-a-file feature.

## Architecture

### Category structure

`settings_view.py`'s `render()` switches from one flat scroll of
`st.divider()`-separated sections to `st.tabs` (same pattern already
proven in `chesswright_pro/srs_drills.py`'s 3-tab structure):

1. **Account & Data** — existing: Lichess/chess.com identity, DB import.
   Unchanged content, just moved under this tab.
2. **Analysis Engine** — existing Live Engine (interactive) form,
   **new** Engine location control, **new** Engine Profiles.
3. **Analytics & Display** — **new**: timezone offset, confidence/
   sample-size threshold.
4. **Ingestion** — **new**: variant policy, queue strategy.
5. **Advanced** — collapsed (`st.expander`, default closed), generic
   editor for the long tail described below.
6. **Anthropic API key**, **Chesswright Pro**, **Support** — existing
   content, unchanged, one tab each (or grouped as sub-tabs under a
   single "Account" area if that reads better at implementation time —
   left as an implementation-time call, not load-bearing to this design).

A text input above the tabs filters/highlights sections and fields by
substring match against a small static registry of `(tab, field label,
help text)` tuples — reuses `rapidfuzz` (already a dependency via
Global Search, `dashboard/data/search.py`) for the same ranked-match
behavior Global Search already gives users elsewhere in the app, rather
than introducing a second, different fuzzy-match convention. Zero new
dependency, zero new persisted index — mirrors Global Search's own
"in-memory candidate list, ranked, no index" shape.

### Common tier — new controls

**Engine location** (`engine.path`, shared by both batch and interactive
engine — confirmed via `dashboard/live_engine.py:148`, which reads
`cfg["engine"]["path"]` the same as `worker.py`'s batch path):
mirrors `onboarding_view.py`'s existing engine step exactly, so there's
one UI pattern for "pick a Stockfish binary" in the whole app, not two:
- Show current path, or "auto-detected: `<path>`" via
  `worker.find_engine_path(None)` if `engine.path` is `null`.
- "Re-detect" button re-runs `find_engine_path(None)`.
- Manual override: native file picker (`components.native_file_picker`)
  + `st.file_uploader` fallback for the plain dev workflow, copied into
  the same `engines/` directory onboarding already uses, validated via
  `worker.validate_engine_path` (real UCI handshake) before being
  accepted, saved via `config.set_engine_path`.
- Same untrusted-binary warning copy onboarding already shows.

**Timezone offset** (`analytics.utc_offset_hours`): a single
`st.number_input` (integer, -12..14, matching real UTC offset range)
saved via `_set_section_scalar("analytics", "utc_offset_hours", ...)`
(already generic enough to reuse as-is — no new `config.py` function
needed). Bundled fix, not a separate unit: `dashboard/data/patterns.py`'s
day×hour query gets a `+ utc_offset_hours` adjustment on `hour_utc`
before bucketing, matching what `analytics.py`'s CLI-only
`report_by_hour_bucket` already does for the older report path. Query-time
only — changing this control re-buckets every game's existing `hour_utc`
value on the next query, no re-import or re-analysis needed, no stale
data risk.

**Confidence / sample-size threshold** (`analytics.min_sample_size`):
one `st.number_input` (integer, >=1), saved the same way. Realizes
`dashboard/confidence.py`'s intended "one shared cutoff" design: today
each of its ~6+ call sites hardcodes its own "low" value
(`min_games=5`-shaped literals) passed into `default_thresholds(low)`.
This unit threads `analytics.min_sample_size` through as the shared
default for call sites that don't have a good reason for a different
cutoff (a few may keep a bespoke value if their existing comment
documents a specific reason — e.g. `structure_min_games_per_group` is a
separate, deliberately distinct key already, not folded into this one).
Query-time only, same no-stale-data property as the timezone control.

**Ingestion behavior** (`ingestion.variant_policy`,
`ingestion.queue_strategy`): two `st.selectbox` dropdowns
(`skip`/`include`; `interleaved_by_year`/`chronological`/
`reverse_chronological`), saved via `_set_section_scalar`. Forward-looking
only — affects future syncs/worker runs, not already-ingested games.

### Advanced tier

One collapsed `st.expander`, generic inputs grouped by `config.yaml`
section heading, for everything not covered above and not excluded:
`engine.pv_max_len`, `engine.reuse_evals`, `worker.consecutive_failure_limit`,
`worker.commit_every_n_moves`, `ingestion.berserk_max_clock_fraction`,
`ingestion.backlog_quota`, `ingestion.backlog_quota_window`,
`sync.request_timeout_seconds`, `sync_chesscom.request_timeout_seconds`.
Each gets a type-appropriate widget (`number_input`/`checkbox`) using
`_set_section_scalar` to save — no new per-field `config.py` function
needed, since that helper is already fully generic. This tier exists so
these keys aren't hidden entirely from a user who wants them, without
pretending they're as safe or as commonly-needed as the Common tier
(each keeps its `config.yaml` comment as its `help=` text, so the
"not recommended to change" / "not a sensitive tuning knob" caveats
already written travel with the control).

**Hard exclusion, repeated for emphasis:** `annotation.*` and
`achievements.*` never appear here. See Non-goals.

### Engine Profiles (presets)

Named snapshots of the engine-tuning surface only: batch
`engine.depth/multipv/threads/hash_mb` + all six `interactive_engine.*`
fields. Deliberately narrower than a full config snapshot — matches the
roadmap's own "Laptop / Desktop / Deep Analysis / Tournament Mode"
framing, where what plausibly differs per machine/mode is engine speed
tuning, not analytics display preferences or ingestion policy.

Storage: new `~/.chesswright/engine_profiles.yaml`, sibling to the
existing `~/.chesswright/` layout (`active_profile`, `profiles/`) — a
flat `{profile_name: {depth, multipv, threads, hash_mb, time_sec,
ie_depth, ie_threads, ie_hash_mb, ie_store_threshold,
use_lichess_cloud_eval}}` mapping. New `config.py` functions, same
module, same style as the existing `list_profiles`/`initialize_profile`/
`remove_profile` trio (which manage a *different* concept — Pro's
per-student profiles — so these get distinctly-named functions,
e.g. `save_engine_profile`, `list_engine_profiles`, `apply_engine_profile`,
`delete_engine_profile`, to avoid any confusion with `list_profiles()`
et al.):
- `save_engine_profile(name)` — reads current `engine.*`/
  `interactive_engine.*` values from the live config, writes them under
  `name` in `engine_profiles.yaml`.
- `list_engine_profiles()` — sorted names.
- `apply_engine_profile(name)` — calls `set_engine_setting` x4 +
  `save_interactive_engine` in one action, so applying a profile is
  atomic from the user's perspective (one button, one toast).
- `delete_engine_profile(name)`.

UI (in the **Analysis Engine** tab, below the existing Live Engine
form): a "Save current as…" text input + button, and a selectbox of
saved profiles with **Apply** and **Delete** buttons. The page's own
caption disambiguates the term: *"Engine Profiles save your speed/depth
settings under a name you choose — not the same as Chesswright Pro's
student profiles below, which are separate databases for different
players."*

### Safeguards

- Every new Common-tier numeric control uses `min_value`/`max_value`
  bounds matching `config.yaml`'s own documented safe range (same
  pattern the existing Live Engine form already establishes) —
  applied consistently, not just where it happened to exist already.
- **Reset to defaults**, one button per Common-tier tab, restoring the
  shipped template `config.yaml`'s own values for that tab's keys only
  (reads the packaged template path the same way
  `config.backfill_missing_keys` already does — no second "defaults"
  file to keep in sync).
- **Confirm-before-delete** on Engine Profiles: Delete requires a second
  click on an explicit "Confirm delete" control (same two-step shape
  already used elsewhere in this codebase for irreversible actions),
  not a single button that immediately destroys a saved profile.
- **No silent retroactive effects**: every control added by this design
  is either query-time (timezone, confidence threshold — re-bucket on
  next query, no stale data possible) or forward-looking (engine
  location, ingestion behavior, engine profiles — affect future
  runs/syncs only). This invariant is *why* `annotation.*`/
  `achievements.*` are excluded outright rather than merely bounded —
  they're the one class of setting in `config.yaml` that doesn't have
  this property.

## Testing

- Unit tests for the two new `config.py` behaviors: the
  `analytics.min_sample_size`/`utc_offset_hours`/ingestion-key saves
  (via the already-generic, already-tested `_set_section_scalar`) and
  the four new Engine Profile functions (save/list/apply/delete round
  trip against a temp `engine_profiles.yaml`).
- Unit test for `patterns.py`'s day×hour query with a non-zero
  `utc_offset_hours`, confirming `hour_utc` buckets shift as expected
  (regression test for the bugfix described above).
- Unit test confirming `confidence.py` call sites that adopt the shared
  `min_sample_size` default actually receive the configured value, not
  a stale hardcoded literal.
- `verify-live-dashboard` pass once built: confirm the tabbed Settings
  page renders against the real dev DB, the search filter narrows
  visibly, an Engine Profile round-trips (save → switch away → apply →
  confirm engine settings changed), and Reset-to-defaults restores the
  template values.

## Open questions

None outstanding — all major branch points (config-exposure depth,
preset scope, Notification Service in/out, the Common-tier candidate
list, the search mechanic) were resolved during brainstorming before
this document was written.

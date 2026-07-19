# Settings Page (React) — Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `settings_view.py` ("Settings")
as ⛔ not started, with a specific caveat: "Holds the bring-your-own
Claude API key flow (`keyring` + fallback) — security-sensitive, port
carefully." It is now also the largest single unbuilt page in the
migration: `settings_view.py` (819 lines) covers 8 tabbed areas and ~40
individual config fields.

Per this session's explicit direction, this is a **fresh design**, not a
port of `settings_view.py`'s `st.tabs`/`st.form` structure — the
Streamlit source and `config.py` are read for business logic and
requirements only, per the standing "Streamlit is reference not
blueprint" directive. Every underlying capability is kept; the layout,
navigation model, and search mechanic are designed from scratch, informed
by web research on settings-page UX patterns done during this session's
brainstorm (sidebar-vs-tabs category navigation, command-palette search
as used by Arc/Raycast/Linear).

The `config.py` backend surface this page needs is **already fully
built** — confirmed by reading the current file, not assumed from a
stale plan: `set_analytics_setting`, `set_ingestion_setting`,
`set_engine_setting`, `set_worker_setting`, `set_sync_setting`,
`set_sync_chesscom_setting`, `save_interactive_engine`, `set_engine_path`
/ `reset_engine_path`, and the full Engine Profiles CRUD
(`save_engine_profile`/`list_engine_profiles`/`apply_engine_profile`/
`delete_engine_profile`) all exist and are already exercised by
`settings_view.py`. This design adds no new `config.py` logic — only a
new API surface wrapping it and a new frontend.

## Goals

- Full functional parity with `settings_view.py`: Anthropic API key
  (save/remove, secure-backend warning), DB import, chess.com
  connect/sync/disconnect, engine location + live-engine tuning + Engine
  Profiles, timezone offset + confidence threshold, ingestion policy,
  the Advanced long-tail, Chesswright Pro license management, and the
  Support section.
- A category-based navigation model that scales past the ~8 categories
  and ~40 fields involved, unlike a tab strip.
- A search/find mechanic for a specific setting, without inventing a
  second, unrelated search UI on top of the app's one existing search
  surface (Cmd+K).
- The same safeguards `settings_view.py` already has: bounded numeric
  inputs, per-category reset-to-defaults, confirm-before-delete on
  Engine Profiles.

## Non-goals (explicit)

- **Help Center, Onboarding, Notification Service** — out of scope, same
  as the original Phase 6 Streamlit spec
  (`docs/superpowers/specs/2026-07-11-phase6-settings-design.md`).
- **Any UI for `annotation.*` or `achievements.*`**, at any tier. Both
  bake into stored per-game data (`moves.classification`, achievement
  unlock fairness) — changing either post-hoc would silently desync
  history with no re-evaluation pass forcing consistency. This is a
  data-integrity boundary carried over unchanged from the Phase 6 spec,
  not revisited here.
- **A native OS file dialog for Engine Location / DB Import.** The
  Streamlit build gets this via a pywebview `js_api` bridge
  (`dashboard/components/native_file_picker/`); `react_desktop_app.py`
  has no such bridge today — it only points pywebview at a URL, with no
  JS-callable Python methods exposed. Building that bridge is real new
  scope (touches the packaged-app launcher, needs its own dev-vs-packaged
  testing story) and is explicitly deferred — tracked as future work,
  not silently dropped. Both controls use manual path-text-entry +
  action button instead (Re-detect / Import) for now. `st.file_uploader`'s
  browser-upload fallback is dropped for the same reason — it exists in
  Streamlit only as a substitute for the native dialog in the plain-dev
  workflow, and text-path entry already covers that workflow without it.
- **Full settings export/import.** Only the existing Engine Profiles
  snapshot concept (engine-tuning fields only) — no general
  export-all-settings-to-a-file feature.
- **New `config.py` logic.** Every value this page reads/writes already
  has a backing function; this design only adds thin API routes and a
  frontend.

## Key decisions (from this session's brainstorm + web research)

1. **Category rail + detail pane, not tabs.** A secondary in-page rail —
   distinct from the app's primary `Sidebar` — lists the 8 categories
   with a scrollable detail pane alongside it, routed via nested routes
   (`/settings/:category`). Chosen over (a) a single long scrolling page
   with sticky anchor-nav, and (b) a search-first landing page of
   category cards with no persistent list. Web research on settings-page
   navigation patterns (2026) was consistent: sidebars scale better than
   tabs once category count exceeds ~6 (tabs "become cramped or require
   scrolling"; sidebars "maintain visibility... especially valuable for
   settings with many categories") — this page has 8 categories and ~40
   fields, well past that line. This also isn't a foreign shape in this
   codebase: `AnalysisJobsPage` already established a persistent
   rail + scrollable-content two-pane split (`ControlRail`), and
   `Sidebar.tsx`'s active-item styling (copper left-border on the
   selected `NavLink`) is reused verbatim for the category rail, so the
   page reads as "this app's navigation," not a one-off pattern.
   Real routes also retire a documented Streamlit pain point for free:
   `settings_view.py`'s tab-state handling needed a specific
   `key=`+`on_change="rerun"` workaround because `st.tabs`'
   `default=` argument silently no-ops on reruns after the first mount
   (see that file's own comment, live-verified 2026-07-11) — React
   Router's URL-driven active state has no equivalent gotcha.

2. **Search reuses Cmd+K instead of porting Streamlit's in-page search
   box.** `settings_view.py` has its own `rapidfuzz`-based
   `_render_search_box()`, separate from the sidebar's Global Search
   (which today only navigates *to* the Settings page). The React app
   already has one established search surface — the `CommandPalette`
   (Cmd+K, built on `cmdk`, which does its own fuzzy matching) — with a
   `setting` candidate category that already exists but is stale (6
   entries, all pointing at bare `/settings` with no deep link). Rather
   than add a second, differently-styled search UI specific to this one
   page, this design updates that candidate list to the real ~20-field
   registry, each entry deep-linking to `/settings/:category#field-id`.
   `SettingsShell` scrolls to and briefly highlights (CSS transition)
   the target field on mount when a hash is present. Both
   `lib/navCandidates.ts`'s `STATIC_CANDIDATES` fallback and the live
   Python-side equivalent (`data.SETTINGS_CANDIDATES`, served by
   `GET /api/nav/pages`) are updated together — same "hand-maintained,
   accepted drift risk" tradeoff `navConfig.ts`'s own comment already
   documents for its group bucketing, not a new risk this design
   introduces.

3. **No global toast library — reuse the existing inline
   pending/error pattern.** Nothing in `frontend/` uses a toast system
   today (`settings_view.py`'s `st.toast()` calls have no established
   equivalent to port). `MaintenanceCard`/`AnalysisJobsPage` already
   establish the pattern this app uses for action feedback: a `pending`
   boolean and an `error` string as props, shown inline next to the
   triggering control. Each Settings category's Save button follows the
   same shape — an inline "Saved ✓" that fades after ~2s on success, or
   an inline error message on failure — rather than introducing a new
   dependency for this one page.

## Architecture

### Routing & layout

`/settings` redirects to `/settings/account-data`. `SettingsShell`
(new component) renders `SettingsRail` (left, ~220px, fixed) + a
scrollable detail pane (right), matching `AnalysisJobsPage`'s
`ControlRail` + content split. `SettingsRail` is a list of `NavLink`s
styled identically to `Sidebar.tsx`'s active/inactive states (copper
left-border + tinted background when active). Category → route:

| Category | Route |
|---|---|
| Account & Data | `/settings/account-data` |
| Analysis Engine | `/settings/analysis-engine` |
| Analytics & Display | `/settings/analytics-display` |
| Ingestion | `/settings/ingestion` |
| Advanced | `/settings/advanced` |
| Anthropic API key | `/settings/api-key` |
| Chesswright Pro | `/settings/pro` |
| Support | `/settings/support` |

Each category is its own page component (`AccountDataSettingsPage`,
`AnalysisEngineSettingsPage`, etc.) under `frontend/src/pages/settings/`,
added to `App.tsx`'s route table as children of a `/settings/*` parent
route rendering `SettingsShell`.

### Category content

Functionally a 1:1 field-for-field port of `settings_view.py` (every
field already has a backing `config.py` function — see Context):

- **Account & Data**: DB import (path input → confirm-username step,
  mirroring `db_import.import_database`'s two-step flow exactly —
  import first, then confirm/edit the suggested username before
  switching databases), chess.com connect/sync-now/disconnect.
- **Analysis Engine**: engine location (current/auto-detected path,
  Re-detect button, manual path input + validate-and-save — no native
  Browse, see Non-goals), Live Engine form (time limit, depth, threads,
  hash, store threshold, cloud-eval checkbox — same bounds as
  `settings_view.py`'s `number_input` `min_value`/`max_value` pairs),
  Engine Profiles (save-current-as, saved-profile select + Apply +
  Delete-with-confirm), reset-to-defaults for this category.
- **Analytics & Display**: UTC offset (-12..14), min sample size (>=1),
  reset-to-defaults.
- **Ingestion**: variant policy (skip/include) and queue strategy
  (interleaved_by_year/chronological/reverse_chronological) selects,
  reset-to-defaults.
- **Advanced**: collapsed-by-default section (visually de-emphasized,
  same "not commonly needed" framing as the Streamlit expander) covering
  `engine.pv_max_len`/`reuse_evals`, `worker.consecutive_failure_limit`/
  `commit_every_n_moves`, `ingestion.berserk_max_clock_fraction`/
  `backlog_quota`/`backlog_quota_window`, `sync.request_timeout_seconds`,
  `sync_chesscom.request_timeout_seconds`. Each field's `config.yaml`
  comment carries over as its help text, same as today.
- **Anthropic API key**: current-key status (masked) + secure-backend
  warning, save form, remove button. Same shared-computer caption
  content as `settings_view.py`.
- **Chesswright Pro**: license status/activate/deactivate if
  `chesswright_pro` is importable, upsell copy + Gumroad link otherwise
  — same conditional-import gate as `_render_pro_section`.
- **Support**: static links (GitHub Sponsors, Open Collective).

**Hard exclusion, repeated for emphasis:** `annotation.*` and
`achievements.*` never appear anywhere in this page. See Non-goals.

### API layer

`api/routers/settings.py` currently only has `GET /api/pro-status`,
`GET /api/settings/claude-key-status`, and `GET /api/nav/pages`. New
routes, one `GET` (current values) + `POST` (save) pair per category,
plus category-specific actions:

- `GET/POST /api/settings/analytics` — `utc_offset_hours`,
  `min_sample_size`.
- `GET/POST /api/settings/ingestion` — `variant_policy`,
  `queue_strategy`.
- `GET/POST /api/settings/advanced` — the long-tail fields as one
  bundled payload (matches the Streamlit page's single "Save advanced
  settings" button covering all of them at once).
- `GET /api/settings/engine`, `POST /api/settings/engine/path`,
  `POST /api/settings/engine/redetect`, `POST /api/settings/engine/live`
  (the Live Engine form), `POST /api/settings/engine/reset`.
- `GET /api/settings/engine-profiles`,
  `POST /api/settings/engine-profiles` (save current as `name`),
  `POST /api/settings/engine-profiles/{name}/apply`,
  `DELETE /api/settings/engine-profiles/{name}`.
- `GET/POST/DELETE /api/settings/api-key` (uses `api_key_store.py`
  exactly as `settings_view.py` does — see the security note below).
- `GET/POST/DELETE /api/settings/chesscom` (connect/status/disconnect),
  `POST /api/settings/chesscom/sync`.
- `POST /api/settings/db-import` (path in, returns the suggested
  username + a pending-import id), `POST /api/settings/db-import/confirm`
  (username + pending id in, switches the active database),
  `POST /api/settings/db-import/cancel`.
- `POST /api/settings/pro/activate`, `POST /api/settings/pro/deactivate`
  (only registered/functional when `chesswright_pro` is importable,
  same conditional-import gate as the Python side already uses;
  `GET /api/pro-status` already exists and is reused as-is for the
  upsell-vs-management branch on the frontend).

Pydantic request models per category, `HTTPException(400/404)` for
validation/not-found errors — matching `analysis_jobs.py`'s existing
conventions. Every route is a thin wrapper calling the existing
`config.py`/`api_key_store.py`/`db_import.py`/`sync_chesscom.py`
functions — no new business logic.

**Security note (API key):** the key is still never returned in full to
the frontend — `GET /api/settings/api-key` returns only
`{"configured": bool, "masked": str | null, "secureBackend": bool}`,
mirroring `settings_view.py`'s own `f"{current_key[:6]}...{current_key[-4:]}"`
masking, computed server-side. The raw key only ever travels
frontend→backend on save (POST body, HTTPS not applicable since this is
`127.0.0.1`-only, same trust boundary the Streamlit version already
operates under), never backend→frontend after that.

### Frontend data flow

One hook per category (`useAnalyticsSettings`, `useIngestionSettings`,
`useEngineSettings`, `useEngineProfiles`, `useApiKeySettings`, etc.),
each: fetch-on-mount, expose current values + a `save(values)` that
POSTs and re-fetches on success (or applies the server's echoed values
directly, category-dependent). Save UX per category matches
`MaintenanceCard`'s existing `pending`/`error` prop shape: inline
"Saved ✓" (auto-fades ~2s) on success, inline error text on failure — no
new toast dependency (see Key Decisions above).

### Search integration

`lib/navCandidates.ts`'s `STATIC_CANDIDATES` settings entries (currently
6, stale) are replaced with the real per-field registry — title,
category route, and a field-anchor id, e.g.
`{ category: 'setting', title: 'Local timezone', url_path: 'settings/analytics-display', anchor: 'utc-offset' }`.
`CommandPalette.handleSelect` is extended to also set `location.hash`
when an `anchor` is present. `data.SETTINGS_CANDIDATES` (Python side,
backing `GET /api/nav/pages`) is updated with the matching real list so
the live and static candidate sources agree, same as every other page's
nav-candidate entries already require.

## Testing

- Vitest component tests per category page, mocking `fetch`, matching
  existing `*.test.tsx` conventions (loading/empty/error/happy-path
  states, save button pending/success/error).
- A `SettingsRail`/`SettingsShell` test confirming route → active-item
  highlighting.
- A Cmd+K test: selecting a settings entry with an anchor navigates to
  the right category route and sets the expected hash.
- FastAPI route tests for every new `api/routers/settings.py` endpoint,
  matching `analysis_jobs.py`'s existing test pattern (temp config file,
  assert the right `config.py` function was called / value persisted).
- `verify` skill pass once built: confirm the category rail renders and
  navigates, a value round-trips (save → reload → still shows the saved
  value), an Engine Profile round-trips (save → switch category away →
  apply → confirm engine settings changed), and a Cmd+K settings search
  jumps to and highlights the right field.

## Open questions

None outstanding — scope (full parity), the native-file-dialog gap
(deferred, manual path entry only), the IA (category rail + detail
pane), and the search mechanic (extend Cmd+K, not a separate search box)
were all resolved during this session's brainstorm before this document
was written.

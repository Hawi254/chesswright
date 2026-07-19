# Frontend Rewrite Feasibility Spike — Design

Status: approved by user, pending self-review + doc-review gate
Date: 2026-07-12
Branch: new dedicated branch/worktree off `main` (e.g. `feature/frontend-spike`) — not
`feature/eval-dedup-cache`, which currently has an unrelated concurrent session's
uncommitted work in flight.

## Context

Chesswright's dashboard is Streamlit end-to-end (21+ pages, all backend access via
`dashboard/data/*.py` against a shared DuckDB/SQLite pair). A same-session brainstorm
started out scoped as "close the visual gap between the live Overview page and its
approved mockups" (see `2026-07-12-overview-engine-room-redesign-design.md`), and while
working through the chrome/topbar portion of that gap (the topbar was an explicit
non-goal of that other design), the user concluded Streamlit itself has a real ceiling
for a "looks and feels like a native desktop app" goal — not just a styling gap.

That ceiling is not hypothetical: this codebase already hit it once. BRIEF.md §25
documents that a global `⌘K` keybind was ruled out because Streamlit custom components
render inside sandboxed iframes that can't observe keydown events fired elsewhere on the
page. CSS injection (the mechanism the Overview redesign and this app's whole `theme.py`
system rely on) can recolor and restyle, but Streamlit's full-script-rerun model and lack
of a real client-side state layer mean smooth transitions, reliable fixed/sticky
positioning, and command-palette-style overlays fight the framework rather than working
with it.

Given that, the user wants to explore setting Streamlit aside for the dashboard's UI
layer entirely, on an isolated feature branch, keeping the existing Python backend
(`ingest.py`, `worker.py`, `annotate.py`, `analytics.py`, `db.py`, `dashboard/data/*.py`)
untouched. This is a **feasibility spike**, not a migration commitment — its job is to
surface whether the riskiest unknowns are survivable before any decision to actually
replace Streamlit's 21 pages.

This also reopens a previously shelved decision. `docs/scoping/fastapi-integration-scoping.md`
(2026-07-08) concluded FastAPI was a no-go for Chesswright, explicitly conditioned on
*"only revisit this as a real 'go' if a concrete, currently-felt problem is named (not
hypothetical future needs)."* A separate frontend needing a real HTTP API into the
existing backend is exactly that trigger. The original research already left two things
unresolved that matter here: PyInstaller bundling was only proven on Linux (Windows/macOS
untested), and reconciling a uvicorn/ASGI server with `desktop_app.py`'s SIGTERM/
main-thread constraint under pywebview was never attempted.

## Goals

- Prove — not assume — that a standalone FastAPI service and a React/Vite frontend can
  be stood up alongside the existing Python backend, on this (Linux) dev machine, without
  touching any existing Streamlit page or `dashboard/data/*.py` business logic.
- Re-open `docs/scoping/fastapi-integration-scoping.md` with the new concrete need on the
  record, and update its conclusion — this is real re-scoping work, not a rubber stamp.
- Stand up the thinnest possible real (non-mocked) vertical slice: 2-3 read-only FastAPI
  endpoints wrapping existing `dashboard/data/overview.py` functions, and a React page
  rendering the Overview identity zone (rating, badges, four stat tiles) against that API.
- Explicitly test the two sharpest unresolved risks from the 2026-07-08 research:
  1. Does a uvicorn/ASGI server process coexist cleanly with pywebview's native window
     loop and `desktop_app.py`'s existing SIGTERM handling — clean start, clean shutdown,
     no orphaned processes?
  2. Does PyInstaller bundling still work once FastAPI/uvicorn are added to *this*
     project's actual spec files (`chesswright.spec`, and per
     `chesswright_pro_pyinstaller_spec_gotcha.md`, that Pro rebuilds need the separate
     `chesswright-pro.spec`) — not just the throwaway hello-world bundle from the original
     research?

## Non-goals (explicit)

- **Not a migration plan.** This does not attempt to move any of the other 20 pages,
  does not touch `dashboard/*_view.py`, and does not commit the project to replacing
  Streamlit. A full migration is a separate, later decision and a separate spec if this
  spike succeeds.
- **No frontend stack commitment beyond the spike.** React + Vite is chosen for this
  spike specifically because the toolchain already exists in-repo (the `react-chessboard`
  component), minimizing new tooling risk — not because the long-term stack question
  (left "fully open" by the user) is considered settled by this choice.
- **No auth, no write endpoints.** All spike endpoints are read-only wrappers over
  existing query functions.
- **No Windows/macOS validation.** This dev environment is Linux-only. The spike can
  prove (or disprove) the Linux path; Windows/macOS packaging risk remains explicitly
  open afterward, not silently assumed solved by a Linux-only result.
- **No production polish.** No auth UI, no error-state design pass, no attempt to match
  the Engine Room visual redesign — a bare, functional page proving the data path is
  enough.
- **No change to `dashboard/data/*.py` itself.** The API layer wraps existing functions
  as-is; if a function's shape is awkward to expose over HTTP, that friction is a finding
  to report, not a license to refactor the data layer mid-spike.

## Approach

**1. Isolate.** New branch/worktree off `main`, independent of `feature/eval-dedup-cache`.

**2. Re-scope FastAPI for real.** Update `docs/scoping/fastapi-integration-scoping.md`
with the new concrete driver (separate-frontend HTTP API need) and an explicit decision:
standalone FastAPI service (the user's choice), not Streamlit's `st.App` ASGI extension
point that the original research flagged as the cheaper fallback. The updated scoping
doc should record the reasoning explicitly: a real SPA rewrite is a bigger, more
permanent commitment than the "expose one HTTP route" case `st.App` was scoped for, so
the extra framework/bundling surface is accepted deliberately here, not overlooked.

**3. Backend slice.** A new top-level `api/` directory (sibling to `dashboard/` and the
new `frontend/` from step 6) — a FastAPI app with 2-3
endpoints — e.g. headline stats, rating trajectory — each a thin wrapper calling the
existing `dashboard/data/overview.py` functions through the existing connection-getting
pattern (`_common.get_connections()` or equivalent). Run it standalone first (plain
`uvicorn` invocation) to validate the API itself before touching packaging.

**4. Process-model reconciliation.** Once the API works standalone, integrate it with
`desktop_app.py`'s process model: start uvicorn in a background thread/process alongside
pywebview's native window loop, and verify clean shutdown on the same SIGTERM path
`desktop_app.py` already handles. This is the step most likely to surface a real blocker.

**5. Packaging.** Add FastAPI/uvicorn to `chesswright.spec` (not `chesswright-pro.spec`
— this spike stays in the public/core repo) and confirm a frozen build still starts,
serves, and shuts down cleanly on Linux.

**6. Frontend slice.** A new `frontend/` directory (Vite + React), one page rendering the
Overview identity zone against the real running API — real data, no mock fixtures.

## Success criteria

- Standalone FastAPI service serves real data from at least 2 endpoints backed by
  unmodified `dashboard/data/overview.py` functions.
- `desktop_app.py` integration: server starts and stops cleanly under the existing
  SIGTERM handling, verified by actually killing the process and checking for orphans
  (not just "it didn't crash during manual testing").
- A PyInstaller-frozen build (Linux) including the FastAPI/uvicorn dependency starts,
  serves the API, and shuts down cleanly.
- The React page renders real Overview data (rating, stat tiles) fetched from the live
  API, not a static fixture.
- `docs/scoping/fastapi-integration-scoping.md` is updated with the new conclusion and
  the evidence gathered here, so a future session doesn't have to re-derive it.

## Open risks carried forward (not resolved by this spike)

- Windows/macOS PyInstaller bundling of FastAPI/uvicorn — untested by this spike (Linux
  dev machine), was already untested by the original 2026-07-08 research.
- Whether a full 21-page migration is actually worth the cost this spike doesn't
  estimate — that's a separate decision after the spike's findings are in.
- Long-term frontend stack choice — React/Vite here is a spike-expedience choice, not a
  final answer.

# Opponent Prep page — design spec

**Date:** 2026-07-16
**Streamlit source:** `dashboard/prep_view.py` (⛔ not started in the migration tracker as of this spec)
**Status:** design approved, not yet implemented

## Why a fresh design, not a port

`prep_view.py` scouts a lichess opponent — fetch their public games, run
Stockfish analysis locally in an isolated per-opponent DB
(`{db}/opponents/{username}/games.db`), then show what they play and where
they go wrong. The Streamlit page renders this as a linear scroll: a form,
then a live-status fragment, then two separate near-duplicate tables
(`get_recent_form` sorted by game count, `get_opening_tendencies` sorted by
blunder rate), then a Pro-gated report container.

Research into real opponent-scouting tools (ChessBase's Style
Report/"quick dossier with recommendations in under a minute", Chess
Stalker, chess.com's opponent Explorer) converges on something Streamlit's
version lacks: a fast, decision-oriented verdict up front, not a stack of
raw tables the user has to read and reconcile themselves. This spec keeps
the same underlying job (fetch → analyze → report) but restructures the
output around that idea, and folds the two overlapping tables into one.

Not a redesign in isolation — it reuses proven primitives already in this
codebase: the `Tabs` primitive (Openings/Matchups/Patterns), the
job-polling shape from `useAnalysisJobStatus`/Analysis Jobs, the
cmdk-based opponent combobox from Matchups' `OpponentPicker`, the
Pro-gate/download mechanics from `GameReportPanel`, and the intensity-bar
idiom for score/blunder columns already used on Openings and Patterns.

## Backend changes

### Merged repertoire query

`dashboard/data/prep.py` currently has two functions computing overlapping
aggregates over the same `(player_color, opening_family)` grouping:

- `get_recent_form()` — n_games, score_pct, avg_cpl; sorted by n_games desc
- `get_opening_tendencies()` — n_games, avg_cpl, blunder_pct; sorted by
  blunder_pct desc

Replace both with a single `get_repertoire(duck_conn, top_n=20)` returning
one DataFrame with all four metrics per (opening, color) group — same two
underlying sub-queries as today (game-grain `games_df` merged with
move-grain `cpl_df`, per the existing comment explaining why those can't
be combined into one GROUP BY), plus a third sub-query/column for
`blunder_pct` added into the same merge. No default sort baked in — the
frontend table controls sort order (see below).

### New routes (new `api/opponent_prep.py`-style section in `api/main.py`, or inline like the existing sections)

- `POST /api/opponent-prep/start` — body `{username, n_games}`. Starts the
  background thread via `opponent_analysis.run_for_opponent`, same
  joblock/job_runner conflict checks `prep_view.py` does today (own batch
  running, external lock held, opponent scout already running) surfaced
  as 409s with a message, not silent failure.
- `GET /api/opponent-prep/status` — polls the module-level thread/lock
  state, shape mirrors `AnalysisJobStatus`: `{status, username, step,
  error}` where `status` is `idle | starting | running | stopping | error
  | done`.
- `POST /api/opponent-prep/stop` — sets the stop event.
- `GET /api/opponent-prep/list` — previously-scouted opponents (scans the
  `opponents/` directory, same logic as `_render_prev_opponents`).
- `GET /api/opponent-prep/report/{username}` — opens the opponent's
  isolated connections via `open_opponent_connections`, returns
  `{gamesAnalyzed, dateRange, colorSplit, repertoire: [...]}` from the
  merged query above. 404 if no opponent DB exists yet.
- `GET /api/opponent-prep/{username}/notes` + `POST
  /api/opponent-prep/{username}/notes/generate` — cached Claude narrative,
  same `get_cached_narrative`/`claude_narrative` plumbing as every other
  narrative feature in this app (Openings, Matchups, Insights). **Not**
  Pro-gated — degrades gracefully to "add your API key in Settings" like
  its siblings.
- `GET/POST /api/opponent-prep/{username}/tournament-report` +
  `download.md`/`download.html` — same Pro-gate/501/403 mechanics as
  `/api/games/{id}/report/*`, delegating to
  `chesswright_pro.tournament_prep` with the opponent's repertoire +
  tendencies + the user's own personal record against them (via the main
  DB's duck connection), exactly as `prep_view.py` does today.

## Frontend structure

### `OpponentPrepPage.tsx`

**Hero.** One combobox (`OpponentPrepSearchBox`, modeled on Matchups'
cmdk-based `OpponentPicker`): typing a name that matches a previously
scouted opponent offers to load their report; typing an unrecognized
username offers "Scout \<name\>" instead. A small "games to fetch"
stepper (default 50, range 10–200) only appears once an unrecognized
username is typed — no permanent always-visible slider.

**Live job state.** While a scout job is running, the hero area shows the
status text + current step label ("Fetching games from lichess...",
"Running Stockfish analysis...", etc. — same `_STEP_LABELS` copy as
today) + a Stop button, in place of the dossier. Driven by a new
`useOpponentPrepStatus` hook copying `useAnalysisJobStatus`'s shape:
2-second poll interval, `connectionLost` flag, fake-timer-testable.
Tabs are hidden/disabled while a job is in flight.

**Dossier strip.** Once a report loads: games analyzed, color split (e.g.
"58 White / 42 Black"), date range of games covered. A thin-data warning
below 5 games, reusing the existing `thin_data_message` copy.

**Tabs** (shared `Tabs` primitive), three instead of the Streamlit page's
two-tables-plus-report:

1. **Repertoire** — the unified table from `get_repertoire()`: Opening,
   Color, Games, Score%, ACPL, Blunder%. Sortable by clicking any column
   header (client-side, no new endpoint), default sort Games desc.
   Score% and Blunder% render as intensity bars (the copper/negative bar
   idiom already used on Openings and Patterns) so weak spots are
   visually obvious by scanning the Blunder% column — no separate
   "Where They Go Wrong" section duplicating the same rows in a
   different sort order.
2. **Scouting Notes** — on-demand Claude summary: generate/regenerate
   button, cached render via `ReactMarkdown`, "Add your API key on
   Settings" fallback when no key configured. Same shape as
   `GameReportPanel` minus the Pro gate.
3. **Tournament Prep Report** — Pro-gated, identical mechanics to
   `GameReportPanel`: `ProUpsell` copy when not licensed, 501 message if
   `chesswright_pro` fails to import, else generate + download
   .md/.html links.

### States to handle

- No username entered yet → empty hero with previously-scouted opponents
  listed as suggestions under the search box (from `.../list`).
- Job running → progress UI in hero, tabs hidden.
- Job error → error banner in hero with the existing "check username
  spelling / Stockfish installed" caption.
- Done, but under 5 games → dossier shows the thin-data warning; table
  and tabs still render whatever rows exist.
- Zero qualifying rows (fewer than 3 games in any opening) → the existing
  "not enough annotated games" info message, unchanged in substance.
- Switching to a different previously-scouted username while idle →
  immediate load from `.../report/{username}`, no re-fetch triggered.

## Routing

Add `OpponentPrepPage` to `navConfig.ts` / `App.tsx`'s component map,
replacing the `PageStub` currently rendered for this page.

## Testing

- Hook tests: `useOpponentPrepStatus`, `useOpponentPrepReport`,
  `useOpponentPrepNotes` — fetch-stub + `vi.useFakeTimers()` convention
  matching `useAnalysisJobStatus.test.ts`, no MSW.
- Page test: `OpponentPrepPage.test.tsx` covering the state list above.
- Backend: pytest coverage for `get_repertoire()` (replacing the existing
  tests for `get_recent_form`/`get_opening_tendencies`) and for the new
  `/api/opponent-prep/*` routes, including the 403/501 pro-gate paths on
  the tournament-report endpoints.
- Live verification: the `verify` skill against the real dev `chess.db`,
  scouting one real lichess username end-to-end — start job, poll to
  completion, confirm the repertoire table, generate Scouting Notes, and
  confirm the Tournament Prep Report gate renders correctly for the
  current (non-Pro) dev state.

## Explicitly out of scope

- No icicle/tree visualization for the repertoire — a richer sortable
  table was chosen over the tree view used elsewhere (Opening Tree, Game
  Endings).
- No time-control filtering/dimension added to the repertoire query —
  the merge only combines the two existing queries' metrics, it doesn't
  add a new grouping dimension.
- Tournament Prep Report's actual report content/generation logic is
  unchanged — this spec only covers wiring its existing
  `chesswright_pro.tournament_prep` call to a real endpoint + download
  links, not redesigning the report itself.

# Overview Identity Zone — Frontend Rewrite Port (Design Spec)

**Date:** 2026-07-12
**Status:** approved, ready for implementation planning.

## Context

The app-shell slice (`docs/superpowers/specs/2026-07-12-app-shell-slice-design.md`,
built and live-verified 2026-07-12) proved the React/Vite + FastAPI stack can do a
real global ⌘K and reproduce the existing 19-page nav exactly, but every route still
renders a `PageStub` placeholder. Per
`docs/scoping/frontend-rewrite-development-path-2026-07-12.md`'s own risk-ordering,
Overview is next: "already spiked, cheap to port, low risk — re-validates the
existing `tests/integration/test_api_overview.py` slice against the real chosen
stack."

"Cheap to port" undersells the current page, though. The original 3-endpoint spike
(`headline-stats`, `rating-trajectory`, `rating-snapshot`) predates the Overview
redesign documented in
`docs/superpowers/specs/2026-07-12-overview-engine-room-redesign-design.md`, which
restructured the page into three zones — identity, evolution (charts), coaching
(findings) — plus an auto-generated career narrative, achievements, a live
engine-status strip, and a "career highlight" teaser linking to Game Detail (a
hidden route with no equivalent in the new frontend's `STATIC_CANDIDATES` at all).
Porting the whole page in one slice would be a much bigger unit of work than the
app-shell slice, with more that can go wrong before the first live-verify.

## Decision: identity zone only, this slice

This slice ports **only the identity zone** — headline stats, rating snapshot,
current streak, and the career narrative paragraph, plus the top-3 strength/weakness
trait tags. Evolution (rating/ACPL charts, win-rate-by-color) and Coaching (the full
findings list, severity tags) are explicitly deferred to their own follow-on slices.
Achievements badges, the live engine-status strip, and the career-highlight teaser
(which needs a Game Detail route this slice does not add) are also out of scope here.

This mirrors the app-shell slice's own discipline: one small vertical slice,
thin backend wrappers, live-verified, committed — rather than a big-bang port.

**Visual scope:** this slice does not chase pixel parity with the current page's
custom CSS (`.cw-ov-rail`, the copper/cyan color scheme, etc.). It reimplements the
identity zone's content functionally equivalent, styled with the already-ported
`THEME` tokens and Tailwind. Getting data and behavior right is the point; visual
polish is cheap to revisit once more pages exist to establish a real design language
for the new stack.

## Backend: three new endpoints

Same thin-wrapper style as `/api/nav/pages` — no changes to `dashboard/data/*.py`
except where noted below. All added to `api/main.py`, alongside the existing 3
Overview endpoints.

- **`GET /api/overview/current-streak`** — wraps `data.get_current_streak(duck_conn)`
  as-is. Returns `{outcome: string | null, length: int}` (a full, unsorted
  `db.games` scan, no joins or window functions — cheap, no caching needed, unlike
  the narrative endpoint below).
- **`GET /api/overview/career-findings`** — wraps
  `data.get_career_findings(duck_conn, sqlite_conn, baseline_blunder_rate)`. The
  endpoint computes `baseline_blunder_rate` internally by calling
  `data.get_headline_stats` first (mirrors what `overview_view.py` already does —
  not exposed as a query param). Returns the full findings list (list of
  `{title, headline, detail, polarity, severity, ...}` dicts) as-is; the frontend
  derives the top-3 trait tags client-side (`(strengths + weaknesses).slice(0, 3)`,
  same logic as `_split_by_polarity` in `overview_view.py`). Returning the full list
  rather than a pre-sliced one is deliberate: a later Coaching-zone slice will want
  the same full payload this endpoint already provides, with no backend change
  needed at that point.
- **`GET /api/overview/narrative`** — wraps
  `narrative.generate_career_narrative(stats, rating_df, top_game)`. The endpoint
  computes all three inputs internally: `get_headline_stats`, `get_rating_trajectory`,
  and `top_game` (the first row of `get_game_explorer_table`, sorted by
  `drama_score` — same as `overview_view.py`'s `top_game = explorer_df.iloc[0]`).
  Returns `{narrative: string}`.

### Performance: TTL cache on narrative and career-findings

Two of the three new endpoints wrap genuinely expensive queries, checked directly
against the actual code rather than assumed:

- `get_game_explorer_table` (used internally by the narrative endpoint to get
  `top_game`) calls `get_game_badges`, whose own docstring documents a ~600ms
  window-function scan over the full `moves` table on this DB's 32k games, plus a
  full `games` table select, merge, and sort on top.
- `get_career_findings` calls `_fetch_move_correlates`, a scan over the full
  **2.3M-row** `moves` table, then runs roughly a dozen more finding-specific
  queries on top (`_nemesis`, `_best_matchup`, `_giant_killing`,
  `_tactical_highlights`, `_game_endings`, `_bishop_color_endings`, ...).
  `_fetch_move_correlates`'s own docstring notes the *optimized* cost is still on
  the order of seconds for a career-findings call on this DB.

(`current-streak`, by contrast, is a single flat `SELECT ... ORDER BY` over
`db.games` with no joins or window functions — genuinely cheap, confirmed by
reading the query directly, no caching needed.)

The Streamlit page only pays these two costs once per session via `st.cache_data`.
The FastAPI layer has no caching at all today — every request to either new
endpoint would re-pay its full cost from scratch on every page load, which is a
real regression versus current behavior, not a neutral port.

`api/db.py`'s `get_db_connections()` already returns a stable, process-wide
singleton `duck_conn` (via `_common.py`'s `st.cache_resource`, confirmed safe
outside Streamlit by the existing `test_get_connections_works_outside_streamlit`
test), which makes a small in-process cache straightforward to add correctly.

**Fix:** a small hand-written TTL cache (60s), applied to both the narrative and
career-findings endpoints' responses — not a general caching framework, and not
applied to `current-streak`, which has no evidenced cost problem. 60s bounds
staleness to roughly one minute after a mid-session sync or analysis batch changes
the underlying data, rather than caching until process restart (`functools.
lru_cache` with no TTL was considered and rejected for this reason).

## Frontend: OverviewPage + useOverviewData

**`useOverviewData()`** (`frontend/src/hooks/useOverviewData.ts`) — fires all 5
Overview fetches in parallel (the existing `headline-stats`/`rating-snapshot` plus
the 3 new endpoints above), same hook-shape convention as `usePageCandidates`.
Returns:

```ts
interface OverviewData {
  stats: HeadlineStats | null
  ratingSnapshot: RatingSnapshot | null
  streak: Streak | null
  findings: Finding[] | null
  narrative: string | null
  loading: boolean
  error: boolean
}
```

Unlike `usePageCandidates`, there is no meaningful static fallback for personal
stats. If any of the 5 requests fail, the hook reports a single page-level `error`
state rather than a patchwork of partial content — the zone's pieces are
interdependent enough (e.g. the "at peak" trend needs `ratingSnapshot`, tags need
`findings`) that partial rendering would look broken rather than gracefully
degraded.

**`OverviewPage`** (`frontend/src/pages/OverviewPage.tsx`) replaces the `PageStub`
currently rendered at the `/overview` route in `App.tsx`. Renders one of: a loading
indicator, an error message, or the full identity zone — trait tags (top 3
strength/weakness findings), current rating + peak/streak line, the narrative
paragraph, and the 4 metric cards (Total games, Analyzed games, Win rate, ACPL).

## Testing plan

- **Backend:** extend `tests/integration/test_api_overview.py` with 3 new endpoint
  tests (same `api_client` fixture pattern as the existing tests and as
  `test_api_nav.py`), including:
  - The narrative endpoint's empty-DB response text, asserted verbatim against
    `narrative.py`'s own docstring: `"No games yet -- fetch some games to get
    started."`
  - A test per cached endpoint (narrative, career-findings) confirming the TTL
    cache actually avoids recomputation on a second call within the 60s window
    (e.g. monkeypatching/counting calls into the underlying expensive function).
- **Frontend:**
  - `useOverviewData.test.ts` — mocked `fetch`, covering loading, success, and
    error states (same style as `usePageCandidates.test.ts`).
  - `OverviewPage.test.tsx` — mocked hook, asserts the metric cards, streak/rating
    line, trait tags, and narrative paragraph all render from sample data; separate
    cases for the loading and error states.
- **Live verification:** Playwright against the real dev DB, cross-checking the
  numbers and narrative text shown against what the current Streamlit Overview page
  shows for the same DB — a correctness sanity check, not a pixel-diff. Also confirm
  the TTL cache is effective on both cached endpoints (e.g. compare timing of a cold
  vs. warm request to each).

## Out of scope (deliberately deferred)

- Evolution zone (rating/ACPL trajectory charts, win-rate-by-color chart) — its own
  follow-on slice; pulls in a charting-library decision not needed here.
- Coaching zone (full findings list rendered with severity tags, cross-links to
  other pages) — its own follow-on slice; reuses the same `career-findings` payload
  this slice already fetches.
- Achievements badges, live engine-status strip, and the career-highlight teaser
  (which needs a Game Detail route not yet added to the new frontend's route table).
- Pixel-parity visual styling with the current Streamlit page's custom CSS.

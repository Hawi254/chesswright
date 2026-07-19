# Overview Career Highlight — Frontend Rewrite Port (Design Spec)

**Date:** 2026-07-13
**Status:** approved, ready for implementation.

## Context

The last piece of "finish Overview" (per
`docs/scoping/frontend-rewrite-development-path-2026-07-12.md`'s close-out) is
the career-highlight teaser. Every prior spec touching this page (identity-zone,
milestones-row, evolution-zone) deferred it for the same reason: it links to a
**Game Detail** page/route that does not exist anywhere in the new frontend's
`App.tsx`/`STATIC_CANDIDATES` (`frontend/src/lib/navCandidates.ts`).

Checked directly this session: Streamlit's Game Detail
(`dashboard/game_detail_view.py`, 727 lines) is not a small page — interactive
chessboard, eval graph, move-by-move annotation panel, saved variations,
board-scoped chat, Claude narrative, Pro gating. It is squarely the "board-heavy
interactive pages" category the roadmap doc's own risk-ordering (Phase 3, item
#2) already calls out as its own high-risk unit, not something to backfill as a
side effect of a small teaser slice.

**Decided with the user (2026-07-13):** this slice ports the career-highlight
**card only**, with an inert (disabled, tooltipped) "View this game" affordance
instead of a real link. Game Detail itself remains fully out of scope, to be
designed and built as its own slice under Phase 3's board-heavy work.

**Also decided (2026-07-13): "Recent form" is dropped from the new Overview
page entirely**, not deferred to a follow-on slice as the evolution-zone spec
had left it. Nothing to build or un-build in the frontend (it was never
ported); this just closes out that spec's open item. No change to the
Streamlit page — `overview_view.py`'s own "Recent form" block
(`overview_view.py:229-250`) is untouched, out of scope for this frontend-only
slice.

## Data source: NOT `career-findings`

Checked directly: the Streamlit career-highlight box (`overview_view.py:252-265`,
inside `_render_evolution_zone`) does not use `career_findings` (strengths/
weaknesses) at all. Its `top_game` comes from
`explorer_df.iloc[0]` where `explorer_df = cached_game_explorer_table(duck_conn)`
(`overview_view.py:402-403`) — i.e. `data.get_game_explorer_table(duck_conn)`
(`dashboard/data/game_explorer.py:87-109`), the same source Game Explorer uses:
game headers joined with `game_badges`, sorted by `drama_score` descending.
`/api/overview/career-findings` (already built, used by identity-zone's trait
tags) is unrelated and untouched by this slice.

The Streamlit box renders, in order:
1. Badge chips (`theme.chip_row_html(top_game)`) + `theme.BADGE_LEGEND` caption
   — only if at least one badge is true; skipped entirely otherwise (the
   `if chips_html:` guard).
2. `"vs. {opponent_name} on {utc_date} ({outcome_for_player})"` — always shown
   when a top game exists.
3. A "View this game →" button — real navigation in Streamlit
   (`st.switch_page(detail_page)`); becomes the inert affordance here.

Badge columns (`dashboard/theme.py`'s `BADGE_CHIPS`, ported as a small TS
constant — same precedent as `charts.ts` porting hex color constants):

```
is_comeback       -> "Comeback"       (positive)
is_giant_killing  -> "Giant-killing"  (positive)
is_brilliant_find -> "Brilliant find" (positive)
is_blunder_fest   -> "Blunder-fest"   (negative)
is_nail_biter     -> "Nail-biter"     (neutral)
```

Legend text (`BADGE_LEGEND`, `dashboard/theme.py:216-219`) is a static string —
ported as a TS constant, not returned by the endpoint (same "small maintenance
duplication, matches existing precedent" reasoning as the chart color
constants).

## Backend: one new endpoint

**`GET /api/overview/career-highlight`** — added to `api/main.py`, alongside
the existing 7 Overview endpoints. Thin wrapper: calls
`data.get_game_explorer_table(duck_conn)` (no new `dashboard/data/*.py` code)
and returns the first row (already sorted by `drama_score` descending) as a
single JSON object, or `null` if the table is empty (fresh install / 0 games):

```json
{
  "game_id": "...",
  "opponent_name": "...",
  "utc_date": "...",
  "outcome_for_player": "win" | "loss" | "draw",
  "is_comeback": bool, "is_giant_killing": bool, "is_brilliant_find": bool,
  "is_blunder_fest": bool, "is_nail_biter": bool
}
```

**60s TTL cache**, same `_TTLCache` class the identity-zone slice added for
`narrative`/`career-findings`. `get_game_explorer_table` is a full `games`
table scan joined with `get_game_badges`'s own query and sorted in pandas —
the same "checked directly, genuinely expensive" cost bar those two endpoints
were held to, not the "single indexed query, no cache" bar `current-streak`/
`achievements` used.

## Frontend: useCareerHighlight + CareerHighlight

**`useCareerHighlight()`** (`frontend/src/hooks/useCareerHighlight.ts`) —
independent hook, same shape/pattern as `useMilestones`: local `fetchJson`,
`useState`/`useEffect` with a cancellation flag, `{ game, loading, error }`.
Not folded into `useOverviewData` — no data dependency on identity-zone
fields, and a failure here shouldn't affect the rest of the page (same
reasoning as every other independent Overview hook so far).

**`CareerHighlight`** (`frontend/src/components/CareerHighlight.tsx`) —
rendered in `OverviewPage.tsx` after `EvolutionZone`, matching the old page's
zone content order (identity → milestones → evolution charts → career
highlight; "recent form" is the only piece from that original order that's
gone, per the decision above).

- **Empty and error both collapse to "render nothing"** — same rule as
  `MilestonesRow` (a single card, not a persistent frame like the charts),
  matching Streamlit's own `if top_game is not None:` guard.
- Badge chips row: rendered only if at least one `is_*` flag is true, styled
  as small pills (positive/negative/neutral color classes matching
  `BADGE_CHIPS`'s semantic split — reuse the existing Tailwind color tokens
  already used for win/loss framing elsewhere on this page, no new colors).
  Legend caption shown directly beneath, small/muted text, only when chips
  are shown (matches Streamlit's `if chips_html:` guard wrapping both).
- Line: `vs. {opponent_name} on {utc_date} ({outcome_for_player})`.
- Inert affordance: a visually-button-styled but `disabled` element, label
  "View this game →", with a `title` tooltip
  ("Game Detail isn't built in the new app yet") — communicates intent
  without a dead link or a 404.

## Testing plan

- **Backend:** extend `tests/integration/test_api_overview.py` with a test for
  `/api/overview/career-highlight` — empty-DB case (`null`) and a populated
  case (top row matches the highest `drama_score` game), same `api_client`
  fixture pattern as the other 7 endpoint tests. Also a cache-hit-counting
  test matching the existing `narrative`/`career-findings` TTL cache tests.
- **Frontend:**
  - `useCareerHighlight.test.ts` — mocked `fetch`: loading, success, `null`,
    and error states.
  - `CareerHighlight.test.tsx` — renders the line + chips from sample data;
    renders nothing for `null` or hook-error; chips row absent when no badge
    flags are true; the "View this game" affordance is present but
    `disabled`.
- **Live verification:** Playwright against the real dev DB (32,295 games),
  cross-checking the rendered opponent/date/outcome/badges against the
  current Streamlit Overview page's career-highlight box for the same DB —
  correctness sanity check, not pixel-diff. Also verify the empty-DB case
  (scratch config pointed at a fresh DB) renders nothing without an error.

## Out of scope (deliberately deferred)

- Game Detail page/route itself — its own future slice, Phase 3's
  board-heavy work (chessboard, eval graph, annotations, saved variations,
  board-scoped chat).
- Wiring the "View this game" affordance to real navigation — depends on the
  above.
- Recent form — dropped entirely (see Context), not deferred.
- Coaching zone (full findings list), live engine-status strip — unrelated to
  this slice, remain deferred from earlier specs.

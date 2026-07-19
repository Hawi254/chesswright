# Overview Coaching zone: React port

**Date:** 2026-07-13
**Status:** approved — brainstormed and confirmed by the user 2026-07-13

## Context

Per `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`'s running
"finish Overview" list, this is the last unbuilt Overview zone besides the
live engine-status strip. Milestones, Evolution charts, and Career Highlight
are already ported (see that doc's most recent entries). This slice ports
`dashboard/overview_view.py`'s `_render_coaching_zone` — the "Your coaching
plan" section — into the React rewrite (`worktree-frontend-spike`).

## What the Streamlit version does

`_render_coaching_zone(strengths, weaknesses, findings, sqlite_conn,
insights_page, page_refs)` (`dashboard/overview_view.py:283`) renders four
pieces, in order:

1. **Strengths/weaknesses balance** — two columns, built from the same
   `strengths`/`weaknesses` lists `_split_by_polarity(findings)` already
   computes for the identity zone's trait tags (top 2 `polarity ==
   "strength"`, top 2 `polarity in ("weakness", "mixed")`). Each column
   falls back to a "Nothing surfaced yet" caption when empty.
2. **Ranked focus-areas list** — `weaknesses` sorted by `_SEVERITY_DOTS`
   (`high`→3, `medium`→2, `low`→1) descending, capped at `[:3]`. Since
   `weaknesses` itself is already capped at 2 by `_split_by_polarity`, this
   list is never more than 2 items in practice — an apparent off-by-one in
   the original code, not something this port fixes (parity, not a
   redesign). Each row shows severity dots, title, detail, and — via
   `_FINDING_DEST` (`overview_view.py:116`) — a button linking to the page
   that finding came from (Patterns & Tendencies, Matchups & Opponents,
   Tactical Highlights, or Game Endings), plus a Streamlit-only tab name
   that has no equivalent yet since those destination pages aren't built.
3. **Coaching-plan CTA** — button label toggles between "Get your coaching
   plan →" and "View your coaching plan →" based on whether
   `data.get_cached_narrative(sqlite_conn, "coaching", "recommendations")`
   already has a row (i.e., whether the user has generated the Insights
   page's AI coaching recommendations before). Links to the Insights page.
4. **Quick-links row** — three buttons: Insights, Patterns & Tendencies,
   Openings & Repertoire.

The zone head renders unconditionally; each piece below it degrades
independently (columns/list only render if there's data), but the CTA and
quick-links always render — they're useful with zero findings too.

## Backend

One new thin-wrapper endpoint, matching the existing no-cache lookup
precedent (`current-streak`, `achievements`):

```
GET /api/overview/coaching-plan-status
→ { "cached": bool }
```

Implementation: `bool(data.get_cached_narrative(sqlite_conn, "coaching",
"recommendations"))` in `api/main.py`, alongside the other `/api/overview/*`
endpoints. No TTL cache — it's a single indexed SQLite lookup, same bar as
`current_streak`/`achievements_endpoint`.

No other backend changes. Strengths, weaknesses, and the ranked list all
derive from `findings`, which `useOverviewData()` already fetches via
`/api/overview/career-findings` for the identity zone's trait tags.

## Frontend

**`useCoachingPlanStatus`** (`frontend/src/hooks/useCoachingPlanStatus.ts`)
— independent hook, same shape as `useMilestones`/`useCareerHighlight`:
fetches `/api/overview/coaching-plan-status` once, exposes `{ cached:
boolean | null }`. Independent because it has no data dependency on
`useOverviewData()`'s fields (same reasoning as the other independent
Overview hooks).

**`CoachingZone`** (`frontend/src/components/CoachingZone.tsx`) — props:
`findings: Finding[]`, `cached: boolean | null`. Internally:
- `splitByPolarity(findings)` — ports `_split_by_polarity` (top 2
  strengths, top 2 weakness/mixed). `OverviewPage.tsx`'s existing
  `topTraitTags` helper does a similar split inline; this component gets
  its own copy rather than sharing, since `topTraitTags` additionally
  interleaves+caps at 3 for the identity zone's tag row, a different shape
  than the two-column balance view needs here.
- `FINDING_DEST: Record<string, { path: string; label: string }>` — ports
  `_FINDING_DEST`, dropping the third (tab-name) tuple element, mapped to
  the new app's real `url_path`s: `patterns`→Patterns & Tendencies,
  `matchups`→Matchups & Opponents, `tactical-highlights`→Tactical
  Highlights, `game-endings`→Game Endings.
- Ranked list rows and quick-links use real `<Link>` (react-router-dom),
  same as `Sidebar`/`CommandPalette` — they navigate to real routes that
  currently render `PageStub`, exactly like every other internal link
  built so far in this rewrite. Not inert like `CareerHighlight`'s Game
  Detail link, since that link's target route doesn't exist in the router
  at all; these targets do.
- Renders unconditionally once `findings` has resolved (matches
  `EvolutionZone`'s "always render" rule, not `MilestonesRow`'s
  empty-collapse) — the CTA and quick-links are useful even with zero
  findings. The balance columns and ranked list independently degrade to
  their own empty states within that render.

**`OverviewPage.tsx`** — add `useCoachingPlanStatus()` alongside the
existing hooks, render `<CoachingZone findings={findings ?? []} cached=
{cached} />` after `<CareerHighlight />`.

No Tailwind/CSS parity attempted with `OVERVIEW_CSS`'s bespoke styling
(severity dots, balance-row borders, etc.) — same "no pixel parity" rule
every prior zone slice has followed, using the existing `@theme` tokens
instead.

## Testing

- Backend: extend `tests/integration/test_api_overview.py` with 2 cases
  for `/api/overview/coaching-plan-status` (no cached row → `false`; a row
  inserted via `save_narrative` → `true`).
- Frontend: `useCoachingPlanStatus.test.ts` (success/error), `CoachingZone.
  test.tsx` (empty findings → CTA+quick-links only, no balance/ranked
  sections; populated findings → both columns, ranked list capped at 2,
  correct `Link` targets; both CTA label states).
- Live-verify via Playwright against the real dev DB (32,295 games, per
  the `frontend_spike_worktree_real_chessdb_copy` memory), screenshotting
  the rendered zone and cross-checking rendered strengths/weaknesses/
  ranked-list/CTA-label against the raw endpoint JSON, same discipline as
  every prior slice.

## Out of scope

The live engine-status strip remains the one unbuilt Overview piece after
this slice. Not addressed here.

# Overview Milestones Row — Frontend Rewrite Port (Design Spec)

**Date:** 2026-07-12
**Status:** approved, ready for implementation planning.

## Context

The identity-zone slice
(`docs/superpowers/specs/2026-07-12-overview-identity-zone-port-design.md`, built
and live-verified 2026-07-12) ported only Overview's identity zone, deliberately
deferring five pieces: the Evolution zone (charts), the Coaching zone (findings
list), achievements/milestones, a live engine-status strip, and a career-highlight
teaser (which needs a Game Detail route that does not exist anywhere in the new
frontend yet).

Per `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`'s close-out
question — "finish this page" vs. "move to the next risk-ordered item" — the user
picked "finish this page." Checking current state showed "finish Overview" is
itself five independent pieces with very different dependency profiles, not one
slice:

- **Milestones/achievements row** — cheapest. `achievements.get_unlocked_achievements()`
  is merged on both `feature/eval-dedup-cache` and `worktree-frontend-spike`, and
  already wired into the *Streamlit* `overview_view.py` (as of the Achievements
  Service work landing — see `achievements_service_design_scoped_2026-07-11`
  memory). No new architectural decision needed.
- **Coaching zone** — mostly display-layer, reuses the `career-findings` payload
  the identity-zone slice already fetches, but cross-links point at pages that are
  still `PageStub`s in the new frontend.
- **Evolution zone** — blocked on a charting-library decision for the new stack
  that has never been made (Plotly/Streamlit isn't available here).
- **Engine-status strip** — needs a "live" polling data pattern, architecturally
  different from every request/response endpoint built so far.
- **Career-highlight teaser** — needs an actual Game Detail route/page, confirmed
  absent from `App.tsx`/`STATIC_CANDIDATES` — really its own page, not a
  teaser-sized unit.

Per this project's standing discipline of one small vertical slice at a time
(the same reasoning that split identity zone out of the full page originally),
this spec scopes **only the milestones row** — the cheapest, least-blocked of
the five.

## Decision: milestones row only, standalone section

This slice ports the achievement "milestones" chip row — currently embedded
inside Streamlit's Evolution zone (`overview_view.py`'s `_render_evolution_zone`,
lines ~235-242) — as its own small, standalone section rendered below the
already-ported identity zone on `OverviewPage`. It is **not** nested inside a
scaffolded Evolution-zone shell; that zone does not exist yet in the new
frontend and this slice does not anticipate its layout.

Charts, recent-form ticker, the rest of the Evolution zone, the Coaching zone,
the engine-status strip, and the career-highlight teaser all remain out of
scope, unaffected by this slice.

**Visual scope:** no pixel-parity chase with Streamlit's `.cw-ov-milestone` CSS
— same precedent as the identity-zone slice. Styled with Tailwind against the
existing `@theme` tokens.

## Backend: one new endpoint

**`GET /api/overview/achievements`** — added to `api/main.py`, alongside the
existing 5 Overview endpoints. Thin wrapper around
`achievements.get_unlocked_achievements(sqlite_conn, limit=4)` — same `limit=4`
Streamlit's `cached_unlocked_achievements` already uses, no query params
(matches the existing thin-wrapper convention — e.g. `career-findings` computes
its own internal inputs rather than taking them as params). Returns the list
as-is:

```json
[{"achievement_id": "...", "name": "...", "description": "...", "unlocked_at": "..."}]
```

**No caching.** `get_unlocked_achievements` is a single indexed
`SELECT achievement_id, unlocked_at FROM achievements_unlocked ORDER BY
unlocked_at DESC LIMIT ?` joined against an in-memory `CATALOG` list — the same
"cheap, no evidenced cost problem" bar the identity-zone spec applied to
`current-streak`, not the heavy full-table-scan bar that justified TTL-caching
`narrative`/`career-findings`.

## Frontend: useMilestones + MilestonesRow

**`useMilestones()`** (`frontend/src/hooks/useMilestones.ts`) — independent
fetch of `/api/overview/achievements`, its own `{milestones, loading, error}`
state. Deliberately **not** folded into `useOverviewData`: milestones data has
no dependency on any identity-zone field (unlike e.g. trait tags needing
`findings`), so there is no correctness reason to couple their loading/error
states, and a milestones-fetch failure should not affect identity-zone
rendering or vice versa.

**`MilestonesRow`** (`frontend/src/components/MilestonesRow.tsx`) — rendered in
`OverviewPage.tsx` below the identity zone content, under its own small
heading ("Milestones"). Each chip shows `name` + `unlocked_at` truncated to
`YYYY-MM-DD` (matches Streamlit's `m["unlocked_at"][:10]` slice) — same content
Streamlit shows today. `description` is returned by the endpoint but not
rendered in this pass; available for a cheap tooltip/`title`-attribute
follow-up later, not required now.

**Empty and error states collapse to the same outcome: render nothing.**
- Zero unlocked achievements (e.g. fresh install) → render nothing, matching
  Streamlit's `if milestones:` guard exactly.
- Fetch error (network/API failure) → also render nothing, rather than an
  inline error message. This is a minor secondary widget, not core page
  content — an error banner here would be disproportionate, and the
  identity-zone data (the actual page-critical content) is already unaffected
  since the hooks are independent.

## Testing plan

- **Backend:** extend `tests/integration/test_api_overview.py` with a test for
  `/api/overview/achievements` — empty-DB case (`[]`) and a populated case,
  same `api_client` fixture pattern as the existing 5 endpoint tests.
- **Frontend:**
  - `useMilestones.test.ts` — mocked `fetch`, covering loading, success, error,
    and empty-array states (same style as `useOverviewData.test.ts`).
  - `MilestonesRow.test.tsx` — renders chips from sample data (name + truncated
    date); renders nothing for an empty array.
- **Live verification:** Playwright against the real dev DB (32,295 games),
  cross-checking the milestone chips shown against what the current Streamlit
  Overview page's milestone row shows for the same DB — a correctness sanity
  check, not a pixel-diff.

## Out of scope (deliberately deferred)

- Evolution zone (rating/ACPL trajectory charts, win-rate-by-color chart,
  recent-form ticker) — its own follow-on slice; blocked on a charting-library
  decision not made yet for the new stack.
- Coaching zone (full findings list with severity tags, cross-links) — its own
  follow-on slice.
- Live engine-status strip — needs a live-polling data pattern not yet designed
  for this stack.
- Career-highlight teaser — needs a Game Detail route/page that does not exist
  in the new frontend yet; a bigger unit than a teaser, not scoped here.
- `description` field rendering (tooltip or otherwise) for milestone chips.
- Pixel-parity visual styling with Streamlit's `.cw-ov-milestone` CSS.

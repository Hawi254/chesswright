# Insights Page Redesign — Phase 2, Unit 4: Recent Improvements

Status: pending user review
Branch: worktree-frontend-spike
Depends on: nothing — independent of Units 1–3 and 5, zero new backend.

## Context

The original proposal's "Recent Improvements" item conflated two
different things (Phase 1's deferral already noted this): the
Achievements Service (binary unlock badges, built backend-only
2026-07-11) and period-over-period metric deltas (Unit 3's job). This
unit covers only the achievements half — the metric-delta half is Unit
3, deliberately kept separate.

Checked against the real codebase before scoping: `/api/overview/
achievements` (`api/main.py:167`) and `achievements.get_unlocked_
achievements(conn, limit=4)` already exist and already have a proven
frontend consumer — Overview's `MilestonesRow.tsx` via the
`useMilestones()` hook (`frontend/src/hooks/useMilestones.ts`), built
2026-07-12. This unit reuses both unchanged; there is no new backend
work here at all, only a second, differently-composed frontend consumer
of data that already flows correctly.

`MilestonesRow.tsx` itself is a bare, title-less chip row that renders
`null` on empty (appropriate for Overview, a dense at-a-glance page).
Insights never silently renders nothing elsewhere on the page — every
other section either has real content or an explicit "nothing yet"
message (e.g. `InsightsPage.tsx`'s own top-level empty state, `Rating
Benchmark`'s muted empty state) — so this unit's version needs its own
component with a header and an explicit empty state, not a direct reuse
of `MilestonesRow` as-is.

## Goals

- Give Insights a closing "Recent Improvements" section using the
  achievements data Overview already proves works, with zero new
  backend risk.
- Match Insights' established voice for an empty state rather than
  Overview's silent-`null` pattern.

## Frontend

### New component: `RecentImprovements.tsx`

Props: `milestones: Milestone[]` (the existing `Milestone` type from
`useMilestones.ts`, unchanged). Renders a `ZoneHead` (`eyebrow="Recent
improvements"`, `title="What's unlocked lately"`) followed by the same
chip markup `MilestonesRow.tsx` already uses (copied, not abstracted
into a shared base — the two call sites' surrounding chrome differs
enough, per `frontend-design` conventions already followed elsewhere in
this codebase, e.g. Unit 1's explicit "no reusable citation component"
call) — when `milestones.length === 0`, renders the muted one-line empty
state instead: "Nothing unlocked yet — keep playing and analyzing.",
same voice as `RatingBenchmark`'s and `CoachingZone`'s empty states.

### `InsightsPage.tsx`: `useMilestones()` usage

No change to `useInsightsData.ts` — reuse `useMilestones()` directly as
a second, independent hook call in `InsightsPage.tsx`, exactly how
`OverviewPage.tsx` already calls it standalone
(`const { milestones } = useMilestones()`) rather than folding it into
`useOverviewData()`. Same conditional render Overview already uses —
`{milestones && <RecentImprovements milestones={milestones} />}` — so
the section renders nothing at all while `useMilestones` is still
loading or has errored (`milestones === null`), and only shows
`RecentImprovements`'s own explicit empty state once loading has
actually finished with zero results. This mirrors Overview's existing
loading behavior exactly while still giving Insights (unlike Overview)
a real empty-state message once the `null` phase has passed.

### Page composition (`InsightsPage.tsx`)

Insert `RecentImprovements` as the last section, after
`TrainingQueueTeaser`:

```
HeroInsight
PerformanceSummary
RatingBenchmark
CriticalFindings
StrengthsWeaknesses
CategorizedInsights
InterestingDiscoveries
NarrativePanel (synthesis)
NarrativePanel (coaching)
TrainingQueueTeaser
RecentImprovements       <- new
```

A closing note, not a headline number — matches how Overview's own
`MilestonesRow` sits near the bottom of that page rather than near the
top.

## Non-goals

- No new backend endpoint, table, or achievements-catalog changes — this
  unit is 100% additive on the frontend.
- No shared component extracted between `MilestonesRow` and
  `RecentImprovements` — see the component section above.
- No `limit` other than the existing hardcoded 4 — matches the earlier
  scoping decision to keep this identical to Overview's version rather
  than diverge on item count.
- No change to `dashboard/insights_view.py` (Streamlit).

## Testing

- `RecentImprovements.test.tsx` (new): renders the chip list for a
  populated `milestones` array (assert `ZoneHead` title + chip count),
  renders the muted empty-state copy for `milestones: []`.
- `InsightsPage.test.tsx`: extend for `RecentImprovements`'s presence as
  the last section, mocking `useMilestones` the same way
  `MilestonesRow.test.tsx` already mocks it for Overview.
- Live verification (`verify` skill): both dev servers against the
  worktree's real `chess.db`; confirm the section renders real unlocked
  achievements (the dev DB has some, per Overview's own milestones row
  already showing them) or the empty state if none, zero console errors.

## Open items for the implementation plan to resolve

- None — this unit's scope is fully settled; smallest and lowest-risk of
  the four remaining units, recommended as the first one built.

# Insights Page Redesign — Phase 2, Unit 1: Rating Benchmark

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/superpowers/specs/2026-07-14-insights-page-redesign-phase1-design.md`
(Phase 1, shipped) deferred four of the original 13-section proposal's
sections as having "no backend basis at all": Estimated Rating Impact,
Trend indicators, an interactive relationship graph, and
Achievements-as-"Recent Improvements". Phase 2 tackles all four, as
separate sub-projects (decomposed in this session's brainstorm since
they are independent pieces of infrastructure/methodology, not one
feature):

1. **Rating Benchmark** — this spec.
2. Historical snapshot store (infrastructure; prerequisite for #3 and the
   deltas half of #4).
3. Trend indicators (depends on #2).
4. Achievements → "Recent Improvements" UI (backend already exists,
   independent of 1-3).
5. Interactive relationship graph (independent of 1-4, needs its own
   correlation/causal-analysis methodology).

This spec scopes only #1.

## Why not literal "Estimated Rating Impact" ("+35 Elo if fixed")

Checked against the real codebase and real data before scoping:

- Rating is tracked only as a yearly aggregate
  (`dashboard/data/overview.py`'s `get_rating_trajectory`) plus a
  current/peak snapshot (`get_rating_snapshot`) — no per-game or monthly
  rating series exists.
- ACPL has monthly granularity (`get_progress_by_month`), but blunder
  rate does not — it appears only as static bucket comparisons in
  `insights.py`.
- No regression library is a dependency (`numpy`/`pandas`/`duckdb` only —
  no `scipy`/`sklearn`/`statsmodels`).
- The real dev `chess.db` has 32,295 total games but only ~2.9% analyzed
  (~900-950 analyzed games) — too little, and too confounded by
  everything else that also moves rating (opponent pool, time control,
  variance), to isolate one specific finding's causal marginal effect on
  this single player's own rating history.

Web research this session found a real, citable population-level
relationship: `ELO ≈ 3100·e^(−0.01·ACPL)` (Chess Digits' analysis of
human play, also referenced on Lichess forums), corroborated by Regan &
Haworth's "Intrinsic Chess Ratings" academic work (>0.98 correlation
between ACPL/STDCPL and Elo across large tournament datasets). But the
same source community (Patrick Coulombe / Chess Digits) is explicit that
the relationship is "not a strong" one for predicting an *individual's
outcome from fixing one specific thing* — it relates **overall** ACPL to
rating in aggregate, across many games and players, and cannot be
decomposed to attribute a rating delta to one finding without assuming
that finding's contribution to ACPL is cleanly separable from everything
else, which the data can't support.

**Decision (this session): no per-finding Elo number anywhere.** One
standalone panel shows the player's own overall ACPL against the
formula's implied rating, framed explicitly as a general, cited
correlation — not a personal or per-finding prediction. This is the
"omit rather than fabricate" norm (`confidence.py`, `BRIEF.md`) applied
to a case where the *literal* proposal item has no honest implementation
at the granularity it asks for.

## Goals

- Give the Insights page one honest point of reference for "is my
  accuracy in line with my rating" — using a real, citable formula, the
  player's own already-computed `acpl`, and their already-tracked
  `current_rating`.
- Make the panel's own limitation legible in its own copy (aggregate
  correlation, not causal, not personalized) rather than relying on the
  user to infer it.
- Gate on sample size the same way every other Insights number does:
  omit the implied rating (not show a fabricated-feeling number) when
  there isn't enough analyzed data.

## Backend: `dashboard/data/_shared.py` changes

Add one pure function, next to the existing `_fetchone_scalar` helper:

```python
import math

MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK = 20  # same cutoff as insights.py's
# MIN_BUCKET_MOVES -- the established "is this ACPL number reliable"
# threshold elsewhere in this codebase. Duplicated as a local constant
# rather than imported from insights.py to avoid a _shared.py -> insights.py
# -> _shared.py import cycle (insights.py already imports from _shared.py).


def estimate_rating_from_acpl(acpl: float) -> int:
    """Population-level ACPL-to-rating correlation, not a personal or
    per-finding prediction. Source: Chess Digits' analysis of human play
    (ELO ~= 3100 * e^(-0.01 * ACPL)), corroborated by Regan & Haworth's
    "Intrinsic Chess Ratings" (>0.98 correlation between ACPL/STDCPL and
    Elo across tournament data). The source community is explicit this
    relationship is weak at the level of attributing a rating delta to
    one specific behavior -- do not use this to estimate per-finding
    impact, only this one aggregate reference point."""
    return round(3100 * math.exp(-0.01 * acpl))
```

Modify `get_headline_stats()` to add `implied_rating` and
`rating_confidence`, computed only when `acpl` is available and gated by
`n_moves` (the same `n_analyzed_moves` value the function already
returns):

```python
def get_headline_stats(duck_conn, sqlite_conn):
    total_games = _fetchone_scalar(duck_conn, "SELECT COUNT(*) FROM db.games")
    analyzed_games = _fetchone_scalar(
        duck_conn, "SELECT COUNT(*) FROM db.games WHERE analysis_status='done'")
    n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(sqlite_conn)
    overall_win_pct = _fetchone_scalar(duck_conn, """
        SELECT 100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*)
        FROM db.games WHERE outcome_for_player IS NOT NULL
    """, default=None)

    rating_confidence = None
    implied_rating = None
    if acpl is not None:
        rating_confidence = confidence_tier(
            n_moves, default_thresholds(MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK))
        if rating_confidence != "insufficient":
            implied_rating = estimate_rating_from_acpl(acpl)
        else:
            rating_confidence = None

    return {
        "total_games": total_games,
        "analyzed_games": analyzed_games,
        "acpl": acpl,
        "blunder_rate": blunder_rate,
        "win_pct": overall_win_pct,
        "n_analyzed_moves": n_moves,
        "implied_rating": implied_rating,
        "rating_confidence": rating_confidence,
    }
```

`_shared.py` gains a new import: `from confidence import confidence_tier,
default_thresholds` (the standalone top-level `confidence` module, not
`insights.py` — no cycle).

## Backend: FastAPI endpoints (`api/main.py`)

No changes. `/api/overview/headline-stats` already wraps
`data.get_headline_stats` and passes the two new fields through
automatically. `/api/overview/rating-snapshot` already exists and needs
no changes — it already returns `{current_rating, peak_rating}`.

## Frontend

### `useInsightsData` (`frontend/src/hooks/useInsightsData.ts`)

Add a third parallel fetch to the existing `Promise.all`:
`/api/overview/rating-snapshot` (same endpoint `IdentityZone` already
calls on Overview — reused, not duplicated logic). Return shape gains
`ratingSnapshot: RatingSnapshot | null`.

### `HeadlineStats` type (`frontend/src/hooks/useOverviewData.ts`)

Add two optional fields, matching the backend's conditional presence:

```typescript
export interface HeadlineStats {
  total_games: number
  analyzed_games: number
  acpl: number | null
  blunder_rate: number | null
  win_pct: number | null
  n_analyzed_moves: number
  implied_rating: number | null
  rating_confidence: 'low' | 'medium' | 'high' | null
}
```

### New component: `RatingBenchmark.tsx`

Props: `stats: HeadlineStats`, `ratingSnapshot: RatingSnapshot`. When
`stats.implied_rating !== null`: shows `ratingSnapshot.current_rating`
next to `stats.implied_rating`, a one-line explanation ("Players with
your overall accuracy (X ACPL) typically sit around Y — a general
correlation, not a personal prediction"), and a small citation/caveat
line naming the source. When `stats.implied_rating === null` (gated out
or `acpl` unavailable): a muted one-line empty state, same voice as
`CoachingZone.tsx`'s "Nothing surfaced yet — check back after more games
are analyzed." No other component in this codebase renders an inline
citation today — this is a one-off plain-text line, not new shared
infrastructure.

### Page composition (`InsightsPage.tsx`)

Insert `RatingBenchmark` immediately after `PerformanceSummary`, before
Critical Findings — both `PerformanceSummary` and `RatingBenchmark` are
aggregate/whole-history context, not per-finding, so they belong
together ahead of the per-finding sections:

```
HeroInsight
PerformanceSummary
RatingBenchmark          <- new
CriticalFindings
StrengthsWeaknesses
CategorizedInsights
InterestingDiscoveries
NarrativePanel (synthesis)
NarrativePanel (coaching)
TrainingQueueTeaser
```

## Non-goals

- No per-finding Elo number anywhere on any `InsightCard` — the entire
  point of this spec's methodology decision.
- No new external data dependency beyond the one hardcoded, cited
  formula constant — no API call to an external service, no new Python
  package.
- No reusable "citation" UI component — this is the only place one is
  needed so far; build it inline, generalize later only if a second
  consumer appears.
- The other four Phase 2 sub-projects (historical snapshot store, trend
  indicators, Achievements UI, relationship graph) — separate specs.
- Any change to `dashboard/insights_view.py` (Streamlit) — stays as-is,
  same posture as every other ported page. The Streamlit page never had
  an "Estimated Rating Impact" section to begin with (it predates the
  redesign proposal), so there is no Streamlit-side parity concern here.

## Testing

- No `tests/unit/test_shared.py` exists today — `_shared.py` has no
  dedicated unit test file, and `get_headline_stats` is currently only
  covered via `tests/integration/test_api_overview.py` (DB-backed).
  This spec creates `tests/unit/test_shared.py` (new,
  `@pytest.mark.unit`, no DB) for `estimate_rating_from_acpl`'s pure
  formula spot-checks (e.g. `acpl=0` → `3100`, a known mid-range value).
  `get_headline_stats`'s gating (`implied_rating`/`rating_confidence`
  both `None` when `acpl` is `None`, both `None` when `n_moves` is below
  the low threshold, both populated above it) is added to
  `tests/integration/test_api_overview.py`'s existing headline-stats
  test class, matching how that function is already exercised there.
- `useInsightsData.test.ts`: extend for the third parallel fetch
  (`ratingSnapshot` populated/error).
- `RatingBenchmark.test.tsx` (new): renders current vs. implied rating
  and citation text when populated; renders the muted empty state when
  `implied_rating` is `null`.
- `InsightsPage.test.tsx`: extend for `RatingBenchmark`'s presence in the
  section order.
- Live verification (`verify` skill): both dev servers against the
  worktree's real `chess.db`; confirm the panel shows a real
  current-vs-implied-rating comparison, confirm the empty state if the
  real data happens to fall below the gate, zero console errors.

## Open items for the implementation plan to resolve

- Exact copy for the panel's explanation and citation line — draft
  above is a starting point, not final; confirm tone against the rest of
  Insights' voice at implementation time.

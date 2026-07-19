# Insights Page Redesign — Phase 2, Unit 3: Trend Indicators

Status: pending user review
Branch: worktree-frontend-spike
Depends on: Unit 2 (historical snapshot store) — `metric_snapshots` must
exist and be populated before this unit has any data to read.

## Context

The original 13-section proposal's "Trend indicators" item
("▼0.8% last 90 days") was deferred in Phase 1 for the same reason
"Estimated Rating Impact" was: no historical series exists to diff
against. Unit 2 closes that gap for four headline fields (`acpl`,
`blunder_rate`, `win_pct`, `implied_rating`) — this unit is the read path
and UI on top of it.

**Scope is headline-level only, not per-finding.** `metric_snapshots`
only stores the four fields above; individual findings
(`insights.py`'s `get_career_findings()`) are never snapshotted (Unit 2's
explicit non-goal). A per-finding trend arrow next to an `InsightCard`
would need its own historical series this project has no basis for —
same "omit rather than fabricate" call Unit 1 made for per-finding Elo.
Trend arrows in this unit only ever annotate `PerformanceSummary` and
`RatingBenchmark`'s existing headline numbers.

**90-day window, validated**: web research on dashboard trend design
confirms 30–90 day rolling windows are the standard choice for this kind
of comparison — long enough to smooth single-session noise, short enough
to stay meaningful for a low-volume hobbyist player (Metabase's own
trend-analysis guidance: "long windows of 30-90 days... smoother but
slower to show real changes"). This also matches the original proposal's
literal "last 90 days" framing, so no deviation to justify.

## Goals

- Show, for each of the four headline fields, whether the player's
  current live value is better or worse than it was ~90 days ago —
  using a real stored snapshot, not a recomputed guess.
- Gate cleanly: no `metric_snapshots` row far enough back (fresh install,
  <90 days of history) means no trend shown, not a fabricated "0%"
  or misleading same-day comparison.
- Current value is always the live, already-fetched
  `get_headline_stats()` output — only the historical reference point
  comes from `metric_snapshots`. Never diff two stored snapshots against
  each other; "now" must always be as fresh as everywhere else on the
  page.

## Backend: `snapshots.py` (extends Unit 2's module)

```python
_TREND_WINDOW_DAYS = 90


def get_headline_trend(conn, current_stats: dict) -> dict:
    """current_stats is the live get_headline_stats() dict this call's
    caller already fetched (api/main.py already computes it for the
    /api/overview/headline-stats endpoint) -- passed in rather than
    recomputed here so this module still never needs a duck_conn (see
    Unit 2 spec's Context section) and there is exactly one code path
    that calls get_headline_stats().

    Finds the metric_snapshots row closest to (but not after) 90 days
    ago. Every *_delta is None when no such row exists, or when the
    corresponding current_stats field is itself None (nothing to diff
    against)."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=_TREND_WINDOW_DAYS)).isoformat()
    row = conn.execute("""
        SELECT snapshot_date, acpl, blunder_rate, win_pct, implied_rating
        FROM metric_snapshots
        WHERE snapshot_date <= ?
        ORDER BY snapshot_date DESC LIMIT 1
    """, (cutoff,)).fetchone()

    if row is None:
        return {
            "compared_to_date": None,
            "acpl_delta": None, "blunder_rate_delta": None,
            "win_pct_delta": None, "implied_rating_delta": None,
        }

    compared_to_date, past_acpl, past_blunder, past_win, past_rating = row

    def _delta(current, past):
        return None if current is None or past is None else current - past

    return {
        "compared_to_date": compared_to_date,
        "acpl_delta": _delta(current_stats["acpl"], past_acpl),
        "blunder_rate_delta": _delta(current_stats["blunder_rate"], past_blunder),
        "win_pct_delta": _delta(current_stats["win_pct"], past_win),
        "implied_rating_delta": _delta(current_stats["implied_rating"], past_rating),
    }
```

## Backend: FastAPI endpoint (`api/main.py`)

New `GET /api/overview/headline-trend`, alongside the existing
`headline_stats()`/`rating_snapshot()` handlers:

```python
@app.get("/api/overview/headline-trend")
def headline_trend():
    sqlite_conn, duck_conn = get_connections()
    stats = data.get_headline_stats(duck_conn, sqlite_conn)
    return snapshots.get_headline_trend(sqlite_conn, stats)
```

## Frontend

### `useInsightsData` (`frontend/src/hooks/useInsightsData.ts`)

Add a fourth parallel fetch: `/api/overview/headline-trend`. Return shape
gains `trend: HeadlineTrend | null`.

```typescript
export interface HeadlineTrend {
  compared_to_date: string | null
  acpl_delta: number | null
  blunder_rate_delta: number | null
  win_pct_delta: number | null
  implied_rating_delta: number | null
}
```

### Trend arrow rendering

No new standalone component — a small inline `<TrendArrow delta={...}
goodDirection="down" />` helper (new, `frontend/src/components/
TrendArrow.tsx`) used directly inside `PerformanceSummary.tsx` (next to
ACPL, blunder rate, win %) and `RatingBenchmark.tsx` (next to implied
rating). `goodDirection` is hardcoded per call site — `"down"` for ACPL
and blunder rate, `"up"` for win % and implied rating — since this is
four fixed, known metrics, not a generic reusable polarity system (same
"build inline, generalize only if a second consumer appears" call Unit
1 made for its citation line). Renders nothing when `delta` is `null`.

## Non-goals

- No per-finding trend arrows anywhere on `InsightCard` — see Context.
- No trend on Overview's `EvolutionZone` charts in this unit — those are
  already full historical line charts (arguably a richer trend view than
  a single arrow); a headline trend arrow duplicating that is a separate
  decision for a future unit, not bundled in here.
- No configurable window (30/60/90-day toggle) — fixed 90 days, see
  Context's research citation.
- No change to `dashboard/insights_view.py` (Streamlit) — same posture as
  every other ported page.

## Testing

- `tests/unit/test_snapshots.py` (extends Unit 2's file): `_delta` helper
  and `get_headline_trend`'s None-propagation, using an in-memory sqlite
  connection with hand-inserted `metric_snapshots` rows at known dates.
- `tests/integration/test_api_overview.py`: new test class for
  `/api/overview/headline-trend` — populated case (seed a >90-day-old
  snapshot row, assert real deltas), gated case (no old-enough row,
  assert all-`None` response).
- `TrendArrow.test.tsx` (new): renders up/down arrow + delta text for a
  populated delta in both `goodDirection` orientations (confirm color/
  direction semantics are opposite for ACPL vs. win %), renders nothing
  for `null`.
- `useInsightsData.test.ts`: extend for the fourth parallel fetch.
- `PerformanceSummary.test.tsx` / `RatingBenchmark.test.tsx`: extend to
  assert `TrendArrow` appears when trend data is present.
- Live verification (`verify` skill): requires Unit 2 to have run at
  least one real sync ≥90 days before "now" against the dev `chess.db`
  to show the populated state — if the real dev data can't clear that
  gate at implementation time, verify the gated (no-trend) empty state
  instead and note that honestly, same as Unit 1's live-verification
  entry would have needed to if the 20-move gate hadn't cleared.

## Open items for the implementation plan to resolve

- Exact arrow glyphs/copy for `TrendArrow` (▲/▼ vs. other iconography) —
  confirm against `RatingBenchmark`'s existing visual voice at
  implementation time.
- Whether `compared_to_date` is surfaced in the UI at all (e.g. "vs. 92
  days ago") or stays backend-only for now — lean toward surfacing it
  briefly, since Unit 1's citation-line precedent is "make the panel's
  own limitation legible in its own copy," and an unlabeled arrow with no
  date risks looking like a live-updating stat rather than a fixed
  comparison point.

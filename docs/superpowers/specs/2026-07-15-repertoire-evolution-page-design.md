# Repertoire Evolution Page — Design

Status: approved by user (design sections), pending spec review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `evolution_view.py`
("Repertoire Evolution") as ⛔ not started — the time dimension of the
Openings page: what entered and left the repertoire, when, and whether
each change paid off. Not to be confused with Overview's `EvolutionZone`
component (rating/ACPL trajectory only) or the already-ported "Openings &
Repertoire" page (all-time view, no time dimension).

Per explicit user direction for this page, the Streamlit source
(`dashboard/evolution_view.py`, 245 lines) was read for requirements and
data-layer understanding only, **not** used as a visual/interaction
template — this is a fresh design, going further than the "don't copy
1:1" posture already established for Openings & Repertoire. The
underlying questions stay the same (confirmed with the user): share of
games over time, an adoption/abandonment ledger comparing early-vs-late
windows, and a per-family win-rate + ACPL deep dive. All three still run
off `dashboard/data/evolution.py`'s existing functions.

## Goals

- Answer the same three questions as the Streamlit page, with a genuinely
  new interaction model rather than a three-independent-fragments port.
- Reuse proven infrastructure: `charts.ts` primitives, the `TrendArrow`
  component, the accordion-panel idiom from Patterns & Tendencies, the
  copper-intensity-bar visual idiom from Game Explorer's `drama_score`.
- Keep the backend a thin wrapper per the `port-view-slice` skill's core
  rule, with one explicitly-flagged small exception (see Key decision 2).

## Key decisions (from this session's brainstorm)

1. **Unified timeline board, not tabs or a master-detail grid.** Two
   alternatives were considered and rejected:
   - *Master-detail grid* (reusing the exact `grid-cols-[detail_1fr]`
     layout already proven for Openings & Repertoire's Repeated
     Positions/Repertoire Holes tabs) — most consistent with existing
     pages, but doesn't visually unify the "when" story the page is
     named for.
   - *Tabbed sections* (closest structurally to the Streamlit page's 3
     fragments) — least novel, and reintroduces the redundant-selector
     problem the Openings & Repertoire spec deliberately removed (deep
     dive would need its own family selector, decoupled from the
     ledger).

   Instead: one continuous page. A composition chart at the top (stacked
   bars by quarter) is followed by a list of per-family timeline strips
   that share the *same quarter x-axis*, each expandable inline into a
   win-rate/ACPL deep dive. This directly visualizes "when" a family was
   adopted/dropped instead of encoding it only as ledger text, and reads
   top-to-bottom as one story: big picture → each opening's story →
   expand any one for detail.

2. **One new, small, pure-pandas function: `ledger_period_shares`.**
   Web/design research on streamgraph-vs-stacked-area tradeoffs
   confirmed precision should win over aesthetics here, given the page's
   payoff is a numeric "did this change pay off" read — reinforcing
   quarterly bars (already the Streamlit choice) over a continuous-time
   streamgraph. That same precision requirement is why each timeline
   strip needs real per-quarter data, not just two ledger endpoints
   (early/late). No existing function returns per-quarter share for
   *every* ledger family (only for the composition chart's top-N +
   "Other" bucket, via `period_shares`). `ledger_period_shares(filtered,
   families)` fills this gap, adapted directly from `period_shares`'s own
   zero-fill-across-gaps logic — pure pandas over the already-fetched
   `filtered` frame, no new SQL. This is the one deliberate exception to
   "zero new backend logic"; flagged to and accepted by the user.
3. **Composition chart stays Plotly** (`stackedBarChart`, a new
   `charts.ts` primitive alongside `barChart`/`groupedBarChart`/
   `overlayBarChart`/`differenceBarChart`), matching every other chart on
   the site. The "fresh design" comes from the interaction model and the
   timeline strips, not from replacing the charting library.
4. **Timeline strips are full per-quarter heatmaps, not two-point bars.**
   Considered and rejected: a simple early→late two-point bar (matches
   `ConfidenceBadge`'s width-bar idiom, less to build) — rejected because
   it can't show the *shape* of a change (e.g. a spike-then-fade reads
   identically to a steady rise). Each cell's intensity = that quarter's
   share of games, using the same intensity-scaling idiom as
   `GameExplorerTable`'s `drama_score` bar (opacity driven by a value)
   but applied per-cell and per-family — see Frontend section for the
   color-identity detail.
5. **Deep dive is lazy and per-row, not eager.** The ACPL scan
   (`get_family_acpl_by_period`) is the page's one real per-selection DB
   hit (~0.5–0.9s, per its own docstring). Fetched only when a strip's
   accordion is expanded, cached in that row's local state so
   collapsing/re-expanding doesn't refetch. Multiple rows can be
   expanded simultaneously — no reason to force single-select.
6. **Row order is the ledger's own status order, unchanged**: adopted,
   dropped, rising, fading, stable (`STATUS_ORDER`, already computed by
   `classify_evolution`). No new sort logic.
7. **Share deltas render as plain text, win-rate deltas reuse
   `TrendArrow`.** `TrendArrow` already supports win% as one of its four
   fixed call sites (`goodDirection: 'up'`) — reused as-is for
   `win_early → win_late`. Share-of-games change isn't inherently
   good/bad, so it stays plain text (`12% → 38%`), matching the existing
   `_pct_arrow` formatting convention.

## Backend: FastAPI endpoints (`api/main.py`)

New functions in `dashboard/data/evolution.py`:

```python
def ledger_period_shares(filtered: pd.DataFrame, families: list[str]) -> pd.DataFrame:
    """Per-quarter share-of-games for each of `families` (the ledger's own
    family list, independent of the composition chart's top-N), zero-filled
    across the full period range so every strip aligns to the composition
    chart's quarter axis. Adapted from period_shares's own zero-fill
    logic. Returns long-form: period, label, family, n_games, share."""
    if filtered.empty or not families:
        return pd.DataFrame(columns=["period", "label", "family", "n_games", "share"])
    per_q_totals = filtered.groupby("period")["n_games"].sum()
    all_periods = range(int(filtered["period"].min()), int(filtered["period"].max()) + 1)
    grid = pd.MultiIndex.from_product([all_periods, families],
                                      names=["period", "family"]).to_frame(index=False)
    fam_counts = (filtered[filtered["family"].isin(families)]
                  .groupby(["period", "family"], as_index=False)["n_games"].sum())
    out = grid.merge(fam_counts, on=["period", "family"], how="left").fillna({"n_games": 0})
    totals = out["period"].map(per_q_totals)
    out["share"] = (100.0 * out["n_games"] / totals.where(totals > 0)).fillna(0.0)
    out["label"] = out["period"].map(_period_label)
    return out
```

Re-exported at the `dashboard.data` package level alongside its
neighbors in `dashboard/data/__init__.py`.

In-process bulk-frame cache (mirrors `_cached_period_counts`) plus three
endpoints:

```python
_evolution_counts_cache = _TTLCache(60)     # unkeyed: get_family_period_counts is one bulk scan
_evolution_acpl_cache: dict[tuple, _TTLCache] = {}   # lazily keyed on (family, color, time_control)


def _get_evolution_counts():
    _, duck_conn = get_db_connections()
    return _evolution_counts_cache.get(lambda: data.get_family_period_counts(duck_conn))


@app.get("/api/evolution/summary")
def evolution_summary(color: str, time_control: str | None = None, grouping: str = "family"):
    counts = _get_evolution_counts()
    filtered = data.filter_counts(counts, color, time_control, grouping)
    shares, top = data.period_shares(filtered)
    ledger = data.classify_evolution(filtered)
    strips = data.ledger_period_shares(filtered, ledger["family"].tolist())
    return {
        "total_games": int(filtered["n_games"].sum()) if not filtered.empty else 0,
        "n_periods": int(filtered["period"].nunique()) if not filtered.empty else 0,
        "composition": {"shares": shares.to_dict(orient="records"), "top": top},
        "ledger": ledger.to_dict(orient="records"),
        "strips": strips.to_dict(orient="records"),
    }


@app.get("/api/evolution/family-trend")
def evolution_family_trend(family: str, color: str, time_control: str | None = None):
    counts = _get_evolution_counts()
    filtered = data.filter_counts(counts, color, time_control, "family")
    return data.family_win_trend(filtered, family).to_dict(orient="records")


@app.get("/api/evolution/family-acpl")
def evolution_family_acpl(family: str, color: str, time_control: str | None = None):
    _, duck_conn = get_db_connections()
    key = (family, color, time_control)
    cache = _evolution_acpl_cache.setdefault(key, _TTLCache(60))
    return cache.get(lambda: data.get_family_acpl_by_period(
        duck_conn, family, color, time_control).to_dict(orient="records"))
```

Add `_evolution_counts_cache` and `_evolution_acpl_cache` to
`reset_caches()` alongside the existing cache instances.

## Frontend

### Hooks (`frontend/src/hooks/`)

- `useEvolutionSummary(color, timeControl, grouping)` — wraps
  `/api/evolution/summary`; returns `{ totalGames, nPeriods, composition,
  ledger, strips, loading, error }`, standard `cancelled`-on-unmount
  cleanup, refetches on any filter arg change.
- `useFamilyDeepDive(family, color, timeControl)` — wraps
  `/api/evolution/family-trend` + `/api/evolution/family-acpl` (fired
  together via `Promise.all`, matching `useEvolutionData`'s existing
  pattern); called only from within a strip's expanded state, not
  page-level.

### Components (`frontend/src/pages/EvolutionPage.tsx` + `frontend/src/components/`)

- **`EvolutionPage.tsx`** — filter bar (Playing as: White/Black pills,
  Time control select, Group by: Opening family / ECO section select,
  same 3 controls as Streamlit, existing button/select primitives, no
  new component) → `CompositionChart` → list of `FamilyTimelineStrip`.
  Empty/error states per the Edge Cases section below.
- **`CompositionChart.tsx`** — stacked-bar-by-quarter chart via the new
  `stackedBarChart()` primitive in `lib/charts.ts` (own `.test.ts`
  cases, same pattern as its neighbors). Family colors need one more
  small addition: `frontend/src/lib/theme.ts` has no categorical-series
  palette yet (checked — only single-series tokens like `cwCopper`
  exist there). Port `dashboard/theme.py`'s `CATEGORICAL_SERIES`
  (`["#3987e5", "#c98500", "#9085e9", "#d95926"]`) and
  `CATEGORICAL_OTHER` (`"#8A8F98"`) into `THEME` the same way
  `sequentialGold`/`diverging` were already ported — same by-hand
  duplication tradeoff `theme.ts`'s own header comment already accepts.
  This is a values-only port (no new design decision), used for both
  the composition chart's family segments and each `FamilyTimelineStrip`
  assigning its own family a consistent color across the page.
- **`FamilyTimelineStrip.tsx`** — props: one ledger row + its strip data
  + summary. Renders: family name, status badge (adopted/dropped/rising/
  fading/stable, same icon/text mapping as Streamlit's `_STATUS_TEXT`),
  a CSS-grid row of per-quarter intensity cells aligned to
  `CompositionChart`'s x-axis — each family's cells scale opacity of
  *that family's own* categorical color (same color it has in the
  composition chart when it's one of the top-N; `CATEGORICAL_OTHER`
  gray scale otherwise), tying strip identity back to the chart above
  rather than using one generic hue for every strip — share-arrow text, `TrendArrow` for the
  win-rate delta, games count. Click toggles an inline accordion (reused
  idiom from Patterns & Tendencies) that lazy-calls
  `useFamilyDeepDive` on first expand and renders win-rate + ACPL line
  charts side by side (via existing `lineChart()`), plus the coverage-
  skew warning caption when `get_family_acpl_by_period`'s coverage gap
  check fires. Multiple strips can be expanded at once.

## Edge cases / empty states (mirroring `evolution_view.py`'s own guards)

- No games at all → info message, page stops.
- Filtered-to-empty (color/time-control combo with 0 games) → info
  message.
- `n_periods < 2` → info message encouraging more history (same
  threshold as Streamlit).
- Ledger empty (no family clears `MIN_FAMILY_GAMES`/`MINOR_SHARE_PCT`
  floors) → composition chart still renders; caption below it explains
  why no strips appear.
- Per-strip deep dive: "not enough games/analyzed moves for a trend"
  captions and the coverage-skew warning, same thresholds as the Python
  module already computes (`min_games_per_quarter`,
  `min_moves_per_quarter`, the 2x coverage-skew check).

## Testing

- Python: extend `tests/unit/test_evolution.py` with cases for
  `ledger_period_shares` — zero-fill across gaps, families outside the
  composition chart's top-N still included, empty-input edge case.
- API: smoke tests for `/api/evolution/summary`,
  `/api/evolution/family-trend`, `/api/evolution/family-acpl` against a
  fixture DB, matching the existing `tests/integration` convention.
- React: `EvolutionPage.test.tsx`, `FamilyTimelineStrip.test.tsx`
  (status colors, accordion expand/collapse, lazy-fetch-once behavior),
  `CompositionChart.test.tsx`, `charts.test.ts` cases for
  `stackedBarChart`.
- Live-verify via the `verify` skill against the real dev `chess.db`
  once built.

## Explicitly out of scope

- Drill-export deep link (Drill Export page is itself unported).
- Global Search per-opening deep linking (not wired up anywhere in the
  new frontend yet, per the same decision already made for Openings &
  Repertoire).
- Any new analytical question beyond the three the Streamlit page
  already answers (per user direction — see Context).

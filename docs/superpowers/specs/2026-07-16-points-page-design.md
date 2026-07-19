# Where Your Points Go — Design

Status: approved by user (design sections), pending spec review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `points_view.py` ("Where Your
Points Go") as ⛔ not started. Per explicit user direction, the Streamlit
source (`dashboard/points_view.py`, `dashboard/data/points.py`) was read
for requirements and data-layer understanding only, **not** used as a
visual/interaction template — the same "fresh design" posture already
established for the Repertoire Evolution page, taken further here: the
user was explicitly asked whether the underlying leak taxonomy itself
was open for rethinking (not just the frontend), and said yes, on a
research-driven basis with no fixed complaint about the current model.

The underlying analytics: every fully analyzed game stores a
move-by-move win-probability curve. Read game-shaped instead of
move-shaped, it becomes a per-game points ledger — each game lands in
exactly one of three leak buckets (priority order: failed_conversion,
missed_swindle, failed_hold) or `none`. This is computed entirely by
`dashboard/data/points.py`, already exercised elsewhere in the React app
(`_points_ledger_cache` in `api/main.py` backs Matchups' per-opponent
swindle-rate lookup).

## Research

Web research (2026-07-16) compared visualization metaphors for
"actual vs. potential" decomposition:

- **Waterfall charts**: the standard "P&L walkdown" pattern — precise,
  linear, best when explaining sequential drivers of a single metric.
- **Sankey diagrams**: best when quantities split and merge across
  branching, categorical paths — "where does X leak away" framing,
  explicitly the stronger fit when the underlying data is a categorical
  split (our three mutually-exclusive buckets) rather than a sequence of
  additive steps.
- Neither chess.com nor Lichess exposes a conversion/swindle/hold
  decomposition at all (confirmed directly in `data/points.py`'s own
  docstring and independently via search) — there is no chess-specific
  prior art to anchor to either way.

Given the buckets are categorical (a game is in exactly one, not
"passing through" several in sequence), a Sankey is the better-fitting
metaphor and was chosen over a waterfall. The page's literal name —
"where your points **go**" — is a flow framing, reinforcing the choice.

**Taxonomy verdict**: no compelling case surfaced to change the three
buckets. They're already cross-validated against Matchups' "collapse"
definition (73/73 games, confirmed on the real database). The "fresh
design" mandate is realized entirely through IA, visualization, and
interaction — not through new leak categories.

## Goals

- Answer the same question the Streamlit page answers — where did
  scoreable points actually go, and why — with a genuinely new
  presentation, not a widget-by-widget port.
- Unify what is currently four disconnected metric tiles plus a
  separate three-card bucket row into one legible picture.
- Add real interaction depth (click-to-filter) that the Streamlit page
  didn't have, handling the buckets' uneven data depth (conversion has
  three extra breakdown dimensions + a cause ladder; swindle/hold have
  none) gracefully rather than forcing a uniform structure.
- Reuse proven infrastructure: `charts.ts` primitives (`barChart`,
  `multiLineChart`), `theme.ts` color tokens (`POSITIVE`, `NEGATIVE`,
  `CATEGORICAL_SERIES`), the existing filter-persistence and
  drill-into-Game-Detail idioms already used elsewhere.
- Keep the backend a thin wrapper: every number the page needs is
  already produced by `dashboard/data/points.py`'s existing functions —
  this page adds zero new pandas/SQL logic.

## Page structure

Top to bottom:

1. Title + one-line explainer + time-control filter (`persist_filter`
   idiom, same pattern as every other filtered page).
2. **Hero zone**: Sankey diagram + precise numeric readout side by side.
3. Headline sentence naming the single biggest leak (same intent as
   today's `_headline` — kept as a callout, not absorbed into the
   diagram).
4. Monthly actual-vs-ceiling trend (`multiLineChart`, unchanged from
   today).
5. Failed-conversion detail: peak-advantage band / phase / clock
   remaining (`barChart` × 3, unchanged from today).
6. Why conversions failed: causes + piece/mate detail (`barChart` × 3,
   unchanged from today).
7. Costliest games table (unchanged data/columns; new: filterable by
   clicking a Sankey bucket).
8. Methodology note, collapsible (same content as today's expander).

## The Sankey diagram

Two levels, denominated entirely in **points** so widths mean one
consistent thing throughout — causes are deliberately excluded (see
below), avoiding a diagram that mixes points-width edges with
game-count-width edges while looking like one consistent picture.

- **Root → Kept / Leaked**: Kept = `actual` (points scored), Leaked =
  `leaked` (points given back). Colored `theme.POSITIVE` /
  `theme.NEGATIVE`.
- **Leaked → the three buckets**: sized by each bucket's leaked-points
  sum from `summarize_buckets()`. Each bucket gets a distinct hue from
  the already-ported `CATEGORICAL_SERIES` palette.

This needs zero new backend logic — `summarize_buckets()` plus the
`actual`/`leaked` sums are exactly what today's page already computes.

**Causes stay out of the Sankey.** `get_failed_conversion_causes`
returns reason counts as a percentage of failed-conversion *games*, not
leaked *points* — a third Sankey level here would silently mix units
across levels (points, then games) while visually implying one
consistent "width = points" read throughout. It remains a separate bar
chart in section 6, matching today's page.

**Numeric readout** sits beside the diagram, not inside it: games in
ledger, actual score %, points leaked, ceiling score % — the same four
figures as today's metric tiles, now anchored next to what visualizes
them instead of floating above it. This also keeps the exact numbers
accessible without depending on hovering a Plotly node.

**New interaction**: clicking one of the three bucket leaf nodes (or its
incoming link) filters the Costliest Games table (section 7) to that
bucket, with a "Showing: Failed conversions ✕" chip to clear it. Root,
Kept, and Leaked are not interactive — only the three bucket nodes
carry a click handler, since those are the only nodes with a
corresponding table filter to apply. Purely a client-side filter over
already-fetched data — no new endpoint. Every bucket gets this,
including missed_swindle/failed_hold (which have no other drill-down
section), so the click always does something useful regardless of which
bucket's depth of downstream detail exists.

**New primitive**: `sankeyChart()` in `frontend/src/lib/charts.ts`,
alongside the existing `barChart` / `stackedBarChart` / `icicleChart` —
stays in Plotly, consistent with every other chart on the site.

## Backend / API

One bundled endpoint: `GET /api/points/summary?time_control=...` —
mirrors the Matchups page's "bundle everything the filter affects into
one call" precedent, since `time_control` here cascades into every
section (bucket summary, monthly trend, conversion breakdowns, causes,
costliest games). Thin FastAPI wrapper assembling a response dict from
functions that already exist in `dashboard/data/points.py`:

- `get_points_ledger` (via the already-wired `_points_ledger_cache`) →
  `classify_points_ledger` → filtered by `time_control`
- `summarize_buckets`, `monthly_points`, `conversion_breakdown` × 3
  (`adv_band`, `conv_phase`, `conv_clock`), `get_failed_conversion_causes`
- Costliest-15 slice (`nlargest(15, "leaked")`, same as today's view,
  moved server-side)

Response shape:

```
{
  tc_options: string[],
  n_games: number,
  actual_pct: number,
  leaked_points: number,
  ceiling_pct: number,
  buckets: [{ bucket, n_games, leaked }],
  monthly: [{ month, n_games, actual_pct, potential_pct }],
  conversion_breakdown: { adv_band: [...], conv_phase: [...], conv_clock: [...] },
  causes: { reason: [...], piece: [...], mate: [...] },
  costliest_games: [{ game_id, utc_date, opponent_name, outcome_for_player,
                       bucket, best_chance, leaked, url }]
}
```

`bucket` fields throughout (in `buckets` and `costliest_games`) are the
same raw keys `data.BUCKET_LABEL` maps from today
(`failed_conversion` / `missed_swindle` / `failed_hold`), not display
labels — the frontend does its own label mapping, and the Sankey
click-filter compares on these raw keys so there is exactly one
source of truth for bucket identity between the diagram and the table.

One hook, `usePointsLedger(timeControl)`, one fetch per filter change —
same pattern as `usePatternsSummary`.

## Empty / error states

- No analyzed games at all → same `thin_data_message` info banner as
  today; nothing else renders.
- Selected time control has zero games → "No analyzed games in this
  time control yet," nothing else renders (unchanged from today).
- Games exist but no leaks in the slice (`buckets` empty) → success
  message ("no leaked points found..."); the Sankey is **not** rendered
  at all rather than drawing a degenerate 100%-kept single-branch
  diagram.
- Costliest-games bucket filter chip: if active and a reload (time
  control change) leaves that bucket with zero games, the chip
  auto-clears rather than showing an empty table silently.

## Testing

Same shape as every other ported page:

- Vitest component tests for `sankeyChart()` (node/link construction
  from bucket rows, including the zero-leak-branch omission).
- Hook tests for `usePointsLedger` (mocked fetch, param changes).
- FastAPI endpoint test for `/api/points/summary` (thin-wrapper
  assembly, `time_control` filtering).
- Live-verify against the real dev `chess.db` before calling this done
  (per the `verify` skill), including the click-to-filter interaction.

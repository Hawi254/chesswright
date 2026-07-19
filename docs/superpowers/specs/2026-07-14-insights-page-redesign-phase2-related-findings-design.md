# Insights Page Redesign — Phase 2, Unit 5: Related Findings

Status: pending user review
Branch: worktree-frontend-spike
Depends on: nothing — independent of Units 1–4.

## Context

The original proposal's "interactive relationship graph" (finding →
finding causal links) has no honest data basis: `insights.py`'s findings
are each computed over their own independent population (some from
`moves_df`, some from raw SQL with different denominators — confirmed by
reading every `_*` finding function in `dashboard/data/insights.py`).
There is no shared per-game unit of analysis that would let two findings
be statistically correlated against each other today, and no correlation
library (`scipy`/`sklearn`/`statsmodels`) is a dependency — same
constraint Unit 1 hit with "Estimated Rating Impact."

This spec reduces the ask to what's actually defensible: a small,
hand-authored set of **editorial** relationships between specific named
findings, grounded in real chess research or established chess theory,
never presented as computed statistics. Framed with the same honesty
distinction Unit 1 draws for its citation line — "a general, cited
relationship, not a personal or per-finding prediction."

**Research done before finalizing scope** (see chat history for full
citations): time pressure's effect on blunder rate is real, peer-reviewed
research (Chabris & Hearst 2006; Sigman et al.'s lichess-scale response-
time study; a 68M-game blunder analysis showing blunder-rate spikes at
lichess's exact low-time alarm thresholds) — strong enough to cite
directly. A second candidate pair (opposite-color-bishop endings related
to king-safety findings via "weak color complex" theory) did not survive
scrutiny: weak-color-complex is a middlegame king-safety mechanism
(trading away the bishop defending your king's color complex), while
`_bishop_color_endings` measures technique specifically from
`endgame_ply` onward — different game phase, different mechanism, no
real shared basis beyond both mentioning "bishop color." **Dropped, not
shipped.** Unit 5 ships with exactly one relationship pair. More can be
added later, each held to the same bar — this is a data file, not a
one-time build.

## Goals

- Surface one genuinely evidenced relationship between two of this app's
  own findings, when a player actually has both active.
- Never claim a computed correlation this app doesn't have — editorial
  content only, sourced and citable.
- No interactivity, no graph visualization — a static, textual
  "related to" note is honest about what this actually is; "interactive
  relationship graph" was the literal ask, and this spec explicitly does
  not build that.

## Implementation: frontend-only, no backend

Because the relationship set is a fixed, hand-authored list with no
per-player computation (checking "is finding X present" is something the
frontend can already do against data it has fetched), this needs no new
endpoint, table, or Python module — the entire feature is a static
content file plus a presentational check against the `Finding[]` the
page already has via `/api/overview/career-findings`.

### `frontend/src/lib/relatedFindings.ts` (new)

```typescript
export interface RelatedFindingPair {
  titles: [string, string]
  rationale: string
  source: string
}

// Editorial, not computed -- see docs/superpowers/specs/2026-07-14-
// insights-page-redesign-phase2-related-findings-design.md for the
// research and the "why only one pair" reasoning. Keyed on Finding.title
// (already this codebase's stable per-finding identity -- InsightsPage.
// tsx already uses it as a React key).
export const RELATED_FINDING_PAIRS: RelatedFindingPair[] = [
  {
    titles: ['Clock pressure and blunder rate', 'Piece blunder hot-spot'],
    rationale:
      "Time pressure is a well-documented driver of blunders in chess research. " +
      "If you have both findings, clock pressure may be part of what's driving " +
      'the piece hot-spot too — though this can\'t say how much of the effect is ' +
      'time-driven versus piece-specific.',
    source: 'Chabris & Hearst (2006); lichess-scale response-time and blunder-rate research',
  },
]

export function relatedFindingFor(title: string, presentTitles: Set<string>): RelatedFindingPair | null {
  for (const pair of RELATED_FINDING_PAIRS) {
    if (!pair.titles.includes(title)) continue
    const other = pair.titles.find((t) => t !== title)!
    if (presentTitles.has(other)) return pair
  }
  return null
}
```

### `InsightCard.tsx` changes

`InsightsPage.tsx` already has the full `findings` array in scope
wherever `InsightCard` is rendered. Pass a new optional prop:
`relatedTo?: RelatedFindingPair | null`, computed by the caller via
`relatedFindingFor(finding.title, presentTitles)` (`presentTitles` built
once per render from `findings.map(f => f.title)`, not recomputed per
card). When non-null, render a small muted footer line inside the card:
"Related: {other title} — {rationale}" with a citation-style
`(source)` suffix, visually similar to `RatingBenchmark`'s existing
citation line but scoped to the one card, not a standalone panel.

Only wired into `CategorizedInsights` and `CriticalFindings`'s card
renders (both already iterate `findings` with access to the full list) —
not `HeroInsight`, which renders a single finding without easy access to
"is the paired finding also present" without extra plumbing, and a
relationship footnote on the hero slot would compete with that slot's
existing citation-free, headline-focused framing.

## Non-goals

- No interactive graph, no D3/visualization library, no new frontend
  dependency — a static text line only.
- No computed/statistical relationships — editorial content only, see
  Context.
- No backend endpoint, table, or Python module — see Implementation.
- No relationship pairs beyond the one shipped here without equivalent
  research backing — this file is meant to grow slowly and only with
  real citations, not become a speculative list.
- No change to `dashboard/insights_view.py` (Streamlit).

## Testing

- `relatedFindings.test.ts` (new): `relatedFindingFor` returns the pair
  when both titles are present, returns `null` when only one title is
  present, returns `null` for a title with no configured pair.
- `InsightCard.test.tsx`: extend for the `relatedTo` prop — renders the
  footer line when present, renders nothing extra when `null`/omitted
  (default — existing tests that don't pass `relatedTo` must keep
  passing unchanged).
- `CategorizedInsights.test.tsx` / `CriticalFindings`-equivalent test:
  extend to confirm `relatedFindingFor` is only called once per distinct
  title set, not recomputed pathologically per card (a plain unit-level
  sanity check, not a performance benchmark).
- Live verification (`verify` skill): confirm on the real dev `chess.db`
  whether both "Clock pressure and blunder rate" and "Piece blunder
  hot-spot" are actually active findings for the real data; if so,
  confirm the related-finding footer renders on both cards pointing at
  each other; if the real data doesn't produce both, verify honestly that
  neither card shows a footer (that's the correct gated behavior, not a
  bug) and note which case was actually observed.

## Open items for the implementation plan to resolve

- Exact copy/visual treatment of the footer line — confirm against
  `InsightCard`'s existing density (`p-4`, `text-sm`/`text-[10px]` scale
  already used for `CONFIDENCE_LABEL` etc.) so it doesn't overwhelm a
  `default`-variant card.
- Whether the relationship footer should be bidirectional in one render
  pass or computed independently per card (bidirectional is the
  intended behavior — both cards show the note, pointing at each other —
  confirm this is what `relatedFindingFor` being called per-card
  naturally produces, since it is symmetric by construction).

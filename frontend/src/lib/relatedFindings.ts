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

export interface TrendArrowProps {
  delta: number | null
  goodDirection: 'up' | 'down'
  unit?: string
}

// Small inline helper, not a generic reusable polarity system -- four
// fixed, known call sites (ACPL, blunder rate, win %, implied rating),
// see docs/superpowers/specs/2026-07-14-insights-page-redesign-phase2-
// trend-indicators-design.md's Frontend section.
export default function TrendArrow({ delta, goodDirection, unit = '' }: TrendArrowProps) {
  if (delta === null) return null

  if (delta === 0) {
    return (
      <span data-testid="trend-arrow" className="ml-1 font-mono text-[10px] text-[var(--cw-muted)]">
        flat
      </span>
    )
  }

  const direction = delta > 0 ? 'up' : 'down'
  const isGood = direction === goodDirection
  const glyph = direction === 'up' ? '▲' : '▼'
  const colorClass = isGood ? 'text-positive' : 'text-negative'

  return (
    <span data-testid="trend-arrow" className={`ml-1 font-mono text-[10px] ${colorClass}`}>
      {glyph}
      {Math.abs(delta).toFixed(1)}
      {unit}
    </span>
  )
}

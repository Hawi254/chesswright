import Plot from 'react-plotly.js'
import { stackedBarChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { CompositionShare } from '../hooks/useEvolutionSummary'

export default function CompositionChart({ shares, top }: { shares: CompositionShare[]; top: string[] }) {
  if (shares.length === 0) {
    return <p className="mt-3 text-xs text-[var(--cw-muted)]">No games in this range yet.</p>
  }

  const colors: Record<string, string> = {}
  top.forEach((family, i) => {
    colors[family] = THEME.categoricalSeries[i % THEME.categoricalSeries.length]
  })
  if (shares.some((row) => row.family === 'Other')) {
    colors.Other = THEME.categoricalOther
  }

  return (
    <div className="mt-3">
      <Plot
        {...stackedBarChart(shares, 'label', 'family', 'share', colors, {
          height: 340,
          xTitle: 'Quarter',
          yTitle: 'Share of games (%)',
        })}
        config={{ displayModeBar: false }}
        style={{ width: '100%' }}
      />
    </div>
  )
}

import Plot from 'react-plotly.js'
import ZoneHead from './ZoneHead'
import { multiLineChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { PointsMonthlyRow } from '../hooks/usePointsLedger'

export default function PointsMonthlyTrend({ rows }: { rows: PointsMonthlyRow[] }) {
  if (rows.length < 2) return null

  return (
    <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="Over time" title="Actual vs. ceiling, by month" />
      <p className="mt-2 text-xs text-[var(--cw-muted)]">
        Monthly score against the score with that month&apos;s leaks recovered. Months with fewer than 3
        analyzed games are excluded.
      </p>
      <div className="mt-3">
        <Plot
          {...multiLineChart(
            rows, 'month',
            [
              { y: 'actual_pct', label: 'Actual score %', color: THEME.positive },
              { y: 'potential_pct', label: 'Ceiling %', color: THEME.accentGold },
            ],
            { yTitle: 'Score %', xTitle: 'Month' },
          )}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </div>
    </div>
  )
}

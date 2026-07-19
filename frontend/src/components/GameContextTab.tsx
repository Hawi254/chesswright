import Plot from 'react-plotly.js'
import { usePatternsGameContext } from '../hooks/usePatternsGameContext'
import { barChart, heatmap } from '../lib/charts'
import { THEME } from '../lib/theme'

const HOUR_ORDER = Array.from({ length: 24 }, (_, i) => String(i))
const DAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function GameContextTab() {
  const { data, loading, error } = usePatternsGameContext()
  if (loading || error || !data) return null

  const offset = data.day_hour_heatmap.utc_offset_hours

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
        <p className="font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]">
          ACPL by game phase
        </p>
        <div className="mt-3">
          <Plot
            {...barChart(data.phase_accuracy, 'phase', 'acpl', THEME.negative, {
              xTitle: 'Game phase', yTitle: 'ACPL (lower = more accurate)',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
        <p className="font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]">
          Win rate heatmap: day of week &times; hour of day (UTC{offset >= 0 ? `+${offset}` : offset})
        </p>
        <p className="mt-1 mb-3 text-xs text-[var(--cw-muted)]">
          Hover a cell to see your average rating difference at that day/hour too -- win rate varies
          partly because who you face varies by time of day, not only how you play then.
        </p>
        <Plot
          {...heatmap(data.day_hour_heatmap.cells, 'hour_local', 'day', 'win_pct', THEME.diverging, {
            xOrder: HOUR_ORDER,
            yOrder: DAY_ORDER,
            xTitle: `Hour of day (UTC${offset >= 0 ? `+${offset}` : offset})`,
            yTitle: 'Day of week',
            colorbarTitle: 'Win %',
            valueSuffix: '%',
            hoverExtra: { column: 'rating_diff_display', label: 'Avg rating diff' },
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </div>
    </div>
  )
}

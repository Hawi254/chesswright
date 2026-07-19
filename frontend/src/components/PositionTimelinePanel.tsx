import { useMemo, useState } from 'react'
import Plot from 'react-plotly.js'
import { useOpeningPositionTimeline } from '../hooks/useOpeningPositionTimeline'
import { stackedBarChart } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function PositionTimelinePanel({ fen, color }: { fen: string | null; color: 'w' | 'b' }) {
  const [expanded, setExpanded] = useState(false)
  const { summary, rows, loading } = useOpeningPositionTimeline(expanded ? fen : null, color)

  const chart = useMemo(() => {
    if (rows.length === 0) return null
    const bySan = new Map<string, number>()
    for (const row of rows) bySan.set(row.san, (bySan.get(row.san) ?? 0) + row.n_games)
    const ranked = Array.from(bySan.entries()).sort((a, b) => b[1] - a[1]).map(([san]) => san)
    const colors: Record<string, string> = {}
    ranked.forEach((san, i) => {
      colors[san] = i < THEME.categoricalSeries.length ? THEME.categoricalSeries[i] : THEME.categoricalOther
    })
    return stackedBarChart(rows, 'year', 'san', 'n_games', colors)
  }, [rows])

  if (!fen) return null

  return (
    <div className="border-t border-[var(--cw-line)] p-3">
      <button type="button" onClick={() => setExpanded(!expanded)}
        className="text-xs uppercase tracking-[0.08em] text-[var(--cw-muted)]">
        {expanded ? '▾' : '▸'} How this position changed over time
      </button>
      {expanded && (
        loading ? (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">Loading…</p>
        ) : !summary ? (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">
            Not enough data across multiple years to compare eras yet.
          </p>
        ) : (
          <>
            <p className="mt-2 text-xs text-[var(--cw-text)]">
              Around {summary.split_year}, your dominant move here switched from{' '}
              <strong>{summary.before_san}</strong> to <strong>{summary.after_san}</strong>.
            </p>
            {chart && <Plot {...chart} config={{ displayModeBar: false }} style={{ width: '100%' }} />}
          </>
        )
      )}
    </div>
  )
}

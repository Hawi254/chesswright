import Plot from 'react-plotly.js'
import { groupedBarChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { EndgameMaterialRow } from '../hooks/useEndingSummary'

interface LongRow {
  endgame_type: string
  outcome: 'win' | 'draw' | 'loss'
  pct: number
}

function toLongForm(rows: EndgameMaterialRow[]): LongRow[] {
  return rows.flatMap((row) => [
    { endgame_type: row.endgame_type, outcome: 'win' as const, pct: row.win_pct },
    { endgame_type: row.endgame_type, outcome: 'draw' as const, pct: row.draw_pct },
    { endgame_type: row.endgame_type, outcome: 'loss' as const, pct: row.loss_pct },
  ])
}

export default function EndgameMaterialSection({ rows }: { rows: EndgameMaterialRow[] }) {
  if (rows.length === 0) {
    return <p className="mt-3 text-xs text-[var(--cw-muted)]">Not enough games yet.</p>
  }

  return (
    <div className="mt-3">
      <Plot
        {...groupedBarChart(toLongForm(rows), 'endgame_type', 'outcome', 'pct', {
          height: 300,
          xTitle: 'Endgame type',
          yTitle: '% of games',
          colors: { win: THEME.positive, draw: THEME.accentGold, loss: THEME.negative },
        })}
        config={{ displayModeBar: false }}
        style={{ width: '100%' }}
      />
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {rows.map((row) => (
          <div key={row.endgame_type} className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-3">
            <span className="block font-condensed text-[11px] uppercase tracking-[0.08em] text-[var(--cw-copper)]">
              {row.endgame_type}
            </span>
            <p className="mt-1 text-sm text-[var(--cw-text)]">{row.n_games.toLocaleString()} games</p>
            <p className="mt-1 text-xs text-[var(--cw-muted)]">
              ACPL {row.acpl !== null ? row.acpl.toFixed(1) : '—'} · Blunders{' '}
              {row.blunder_rate !== null ? `${row.blunder_rate.toFixed(1)}%` : '—'}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

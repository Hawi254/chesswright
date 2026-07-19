import Plot from 'react-plotly.js'
import { usePatternsTurningPoints } from '../hooks/usePatternsTurningPoints'
import { barChart } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function TurningPointsTab() {
  const { data, loading, error } = usePatternsTurningPoints()
  if (loading || error || !data) return null

  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
      <p className="font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]">
        When do your losses get decided?
      </p>
      <p className="mt-1 mb-3 text-xs text-[var(--cw-muted)]">
        For each loss, this finds the single move in a contested position (win probability
        between 30-70%) where the most win probability was dropped in one move. Aggregating
        across losses reveals whether your games slip away in the opening, middlegame, or
        endgame -- and whether it happens when the clock is full or when you&apos;re under
        pressure.
      </p>

      {data.n_losses === 0 ? (
        <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
      ) : (
        <>
          <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
            <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              Decisive moment profile
            </p>
            <p className="mt-1 text-xl text-[var(--cw-text)]">
              Typically move {data.median_move} ({data.most_common_phase})
            </p>
            <p className="mt-1 text-xs text-[var(--cw-muted)]">
              Based on {data.n_losses} losses with a contested position
            </p>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4">
            <Plot
              {...barChart(data.by_move_bucket, 'bucket', 'n_losses', THEME.negative, {
                height: 240, xTitle: 'Move number', yTitle: 'Losses',
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
            <Plot
              {...barChart(data.by_phase, 'phase', 'n_losses', THEME.negative, {
                height: 240, xTitle: 'Game phase', yTitle: 'Losses',
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>

          {data.by_clock_bucket.length > 0 && (
            <div className="mt-4">
              <Plot
                {...barChart(data.by_clock_bucket, 'bucket', 'n_losses', THEME.negative, {
                  height: 220, xTitle: 'Clock remaining', yTitle: 'Losses',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
          )}
          {data.n_no_clock_data > 0 && (
            <p className="mt-2 text-xs text-[var(--cw-muted)]">
              {data.n_no_clock_data} of {data.n_losses} losses excluded from clock chart -- no
              clock data for those games.
            </p>
          )}
        </>
      )}
    </div>
  )
}

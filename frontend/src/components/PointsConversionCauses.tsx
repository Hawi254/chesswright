import Plot from 'react-plotly.js'
import ZoneHead from './ZoneHead'
import { barChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import { POINTS_REASON_LABEL } from '../lib/pointsLabels'
import type { PointsLabeledRow, PointsReasonRow } from '../hooks/usePointsLedger'

export default function PointsConversionCauses({
  reason,
  piece,
  mate,
}: {
  reason: PointsReasonRow[]
  piece: PointsLabeledRow[]
  mate: PointsLabeledRow[]
}) {
  if (reason.length === 0) return null

  const reasonPlot = reason.map((r) => ({ ...r, label: POINTS_REASON_LABEL[r.reason] ?? r.reason }))

  return (
    <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="Failed conversions" title="Why conversions failed" />
      <div className="mt-3">
        <Plot
          {...barChart(reasonPlot, 'label', 'pct', THEME.accentGold, {
            xTitle: 'Cause', yTitle: '% of failed conversions',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </div>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-xs text-[var(--cw-muted)]">Which piece hung</p>
          {piece.length === 0 ? (
            <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
          ) : (
            <Plot
              {...barChart(piece, 'label', 'pct', THEME.negative, {
                xTitle: 'Piece hung', yTitle: '% of hung-piece failed conversions',
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          )}
        </div>
        <div>
          <p className="mb-1 text-xs text-[var(--cw-muted)]">How deep the blown mate was</p>
          {mate.length === 0 ? (
            <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
          ) : (
            <Plot
              {...barChart(mate, 'label', 'pct', THEME.negative, {
                xTitle: 'Forced mate distance', yTitle: '% of blown-mate failed conversions',
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

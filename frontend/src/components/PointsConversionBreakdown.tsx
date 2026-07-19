import Plot from 'react-plotly.js'
import ZoneHead from './ZoneHead'
import { barChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { PointsAdvBandRow, PointsConvClockRow, PointsConvPhaseRow } from '../hooks/usePointsLedger'

export default function PointsConversionBreakdown({
  advBand,
  convPhase,
  convClock,
}: {
  advBand: PointsAdvBandRow[]
  convPhase: PointsConvPhaseRow[]
  convClock: PointsConvClockRow[]
}) {
  if (advBand.length === 0 && convPhase.length === 0 && convClock.length === 0) return null

  return (
    <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="Failed conversions" title="Where the leaks concentrate" />
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div>
          <p className="mb-1 text-xs text-[var(--cw-muted)]">By peak advantage</p>
          <Plot
            {...barChart(advBand, 'adv_band', 'leaked', THEME.negative, {
              height: 280, xTitle: 'Advantage at its peak', yTitle: 'Points leaked',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
        <div>
          <p className="mb-1 text-xs text-[var(--cw-muted)]">By phase it became winning</p>
          <Plot
            {...barChart(convPhase, 'conv_phase', 'leaked', THEME.negative, {
              height: 280, xTitle: 'Phase it became winning', yTitle: 'Points leaked',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
        <div>
          <p className="mb-1 text-xs text-[var(--cw-muted)]">By clock remaining at that moment</p>
          <Plot
            {...barChart(convClock, 'conv_clock', 'leaked', THEME.negative, {
              height: 280, xTitle: 'Clock remaining', yTitle: 'Points leaked',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>
    </div>
  )
}

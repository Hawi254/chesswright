import { useState } from 'react'
import Plot from 'react-plotly.js'
import type { AcplPoint, RatingPoint } from '../hooks/useEvolutionData'
import { barChart, coverageWarning, lineChart } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function EvolutionZone({
  ratingTrajectory,
  acplTrajectory,
}: {
  ratingTrajectory: RatingPoint[]
  acplTrajectory: AcplPoint[]
}) {
  const [isOpen, setIsOpen] = useState(true)
  const chartOptions = {
    height: 200,
    paperBgcolor: THEME.cwCanvas,
    plotBgcolor: THEME.cwPanel2,
    axisColor: THEME.cwText,
  }

  const ratingChart = lineChart(ratingTrajectory, 'year', 'avg_rating', THEME.cwCopper, {
    ...chartOptions,
    xTitle: 'Year',
    yTitle: 'Average rating',
  })

  const acplRows = acplTrajectory.map((row) => ({
    ...row,
    hover_coverage: `${row.n_games} of ${row.n_total_games} games (${row.coverage_pct.toFixed(1)}%)`,
  }))
  const acplChart = lineChart(acplRows, 'year', 'acpl', THEME.negative, {
    ...chartOptions,
    xTitle: 'Year',
    yTitle: 'ACPL',
    hoverExtra: { column: 'hover_coverage', label: 'Analyzed' },
  })

  const volumeChart = barChart(ratingTrajectory, 'year', 'n_games', THEME.cwMuted, {
    ...chartOptions,
    xTitle: 'Year',
    yTitle: 'Games played',
  })

  const warning = coverageWarning(acplTrajectory)

  return (
    <div className="mt-5 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        className="flex w-full items-center justify-between text-left"
      >
        <h2 className="font-condensed text-[11px] text-[var(--cw-text)]">
          Rating, accuracy &amp; activity over time
        </h2>
        <span
          aria-hidden="true"
          className={`font-mono text-[10px] text-[var(--cw-muted)] transition-transform motion-reduce:transition-none ${isOpen ? '' : '-rotate-90'}`}
        >
          ▾
        </span>
      </button>
      {isOpen && (
        <>
          <div className="mt-3 grid grid-cols-3 gap-4">
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                Rating
              </div>
              <Plot data={ratingChart.data} layout={ratingChart.layout} config={{ displayModeBar: false }} style={{ width: '100%' }} />
            </div>
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                Accuracy
              </div>
              <Plot data={acplChart.data} layout={acplChart.layout} config={{ displayModeBar: false }} style={{ width: '100%' }} />
            </div>
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                Volume
              </div>
              <Plot data={volumeChart.data} layout={volumeChart.layout} config={{ displayModeBar: false }} style={{ width: '100%' }} />
            </div>
          </div>
          {warning && <p className="mt-2 text-xs text-[var(--cw-muted)]">{warning}</p>}
        </>
      )}
    </div>
  )
}

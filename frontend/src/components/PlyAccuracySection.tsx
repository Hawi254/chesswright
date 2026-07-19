import { useMemo, useState } from 'react'
import Plot from 'react-plotly.js'
import Slider from './ui/Slider'
import { useOpeningsTable } from '../hooks/useOpeningsTable'
import { useOpeningPlyAccuracy } from '../hooks/useOpeningPlyAccuracy'
import type { PlyAccuracyRow } from '../hooks/useOpeningPlyAccuracy'
import { barChart, differenceBarChart, overlayBarChart } from '../lib/charts'
import { THEME } from '../lib/theme'

function label(family: string, color: string): string {
  return `${family} (${color})`
}

export default function PlyAccuracySection() {
  const { openings, loading, error } = useOpeningsTable()
  const [minAppearances, setMinAppearances] = useState(3)
  const [primaryKey, setPrimaryKey] = useState<string | null>(null)
  const [compareEnabled, setCompareEnabled] = useState(false)
  const [compareKey, setCompareKey] = useState<string | null>(null)

  const options = useMemo(
    () => (openings ?? []).map((o) => ({ key: `${o.opening_family}|${o.player_color}`, family: o.opening_family, color: o.player_color })),
    [openings],
  )
  const primary = primaryKey ? options.find((o) => o.key === primaryKey) : options[0]
  const compare = compareKey ? options.find((o) => o.key === compareKey) : null

  const primaryResult = useOpeningPlyAccuracy(primary?.family ?? null, primary?.color ?? null, minAppearances)
  const compareResult = useOpeningPlyAccuracy(
    compareEnabled ? (compare?.family ?? null) : null, compareEnabled ? (compare?.color ?? null) : null, minAppearances,
  )

  if (loading || error || !openings) return null

  const primaryRows: PlyAccuracyRow[] = primaryResult.rows ?? []
  const worst = [...primaryRows].sort((a, b) => b.avg_cpl - a.avg_cpl).slice(0, 3)

  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">
        Average centipawn loss by move number within a specific opening — a spike means your
        choices at that move are costing you more than usual, not just a general feel.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-4">
        <label className="block text-xs text-[var(--cw-muted)]">
          Select opening
          <select
            value={primary?.key ?? ''}
            onChange={(e) => setPrimaryKey(e.target.value)}
            className="mt-1 block w-56 rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-2 py-1 text-[var(--cw-text)]"
          >
            {options.map((o) => (
              <option key={o.key} value={o.key}>{label(o.family, o.color)}</option>
            ))}
          </select>
        </label>
        <div className="w-56">
          <Slider id="ply-min-appearances" label="Min games reaching each move" min={1} max={10} value={minAppearances} onChange={setMinAppearances} />
        </div>
      </div>

      {primaryRows.length > 0 && primary && (
        <>
          <Plot
            data={barChart(primaryRows, 'move_number', 'avg_cpl', THEME.negative, {
              height: 280, xTitle: 'Move number', yTitle: 'Average centipawn loss',
            }).data}
            layout={barChart(primaryRows, 'move_number', 'avg_cpl', THEME.negative, {
              height: 280, xTitle: 'Move number', yTitle: 'Average centipawn loss',
            }).layout}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
          {worst.length > 0 && (
            <p className="mt-2 text-xs text-[var(--cw-muted)]">
              Highest-CPL move numbers: {worst.map((r) => `move ${r.move_number} (avg ${r.avg_cpl.toFixed(0)} CPL, ${r.blunder_rate.toFixed(0)}% blunder)`).join(', ')}
            </p>
          )}
        </>
      )}

      <button
        type="button"
        onClick={() => setCompareEnabled((prev) => !prev)}
        className="mt-4 rounded border border-[var(--cw-line)] px-3 py-1.5 font-condensed text-xs text-[var(--cw-text)] hover:bg-[var(--cw-line)]/40"
      >
        {compareEnabled ? 'Hide comparison' : 'Compare against another opening'}
      </button>

      {compareEnabled && (
        <div className="mt-3">
          <label className="block text-xs text-[var(--cw-muted)]">
            Compare against
            <select
              value={compare?.key ?? ''}
              onChange={(e) => setCompareKey(e.target.value)}
              className="mt-1 block w-56 rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-2 py-1 text-[var(--cw-text)]"
            >
              <option value="">None</option>
              {options.map((o) => (
                <option key={o.key} value={o.key}>{label(o.family, o.color)}</option>
              ))}
            </select>
          </label>

          {compare && compareResult.rows && compareResult.rows.length > 0 && primary && primaryRows.length > 0 && (
            <>
              {(() => {
                const seriesA = { rows: primaryRows, x: 'move_number' as const, y: 'avg_cpl' as const, label: label(primary.family, primary.color), color: THEME.accentGold }
                const seriesB = { rows: compareResult.rows!, x: 'move_number' as const, y: 'avg_cpl' as const, label: label(compare.family, compare.color), color: THEME.positive }
                const overlay = overlayBarChart(seriesA, seriesB, { height: 280, xTitle: 'Move number', yTitle: 'Average centipawn loss' })
                const diff = differenceBarChart(seriesA, seriesB, { height: 240, xTitle: 'Move number' })
                const commonCount = primaryRows.filter((r) => compareResult.rows!.some((c) => c.move_number === r.move_number)).length
                return (
                  <>
                    <Plot data={overlay.data} layout={overlay.layout} config={{ displayModeBar: false }} style={{ width: '100%' }} />
                    <p className="mt-2 text-xs text-[var(--cw-muted)]">
                      {label(primary.family, primary.color)} vs. {label(compare.family, compare.color)}: average
                      centipawn loss by move number, side by side.
                    </p>
                    {commonCount > 0 ? (
                      <>
                        <Plot data={diff.data} layout={diff.layout} config={{ displayModeBar: false }} style={{ width: '100%' }} />
                        <p className="mt-2 text-xs text-[var(--cw-muted)]">
                          Move numbers where both openings have enough games ({commonCount} shared move
                          numbers). Positive bars mean {label(compare.family, compare.color)} loses less
                          here than {label(primary.family, primary.color)}.
                        </p>
                      </>
                    ) : (
                      <p className="mt-2 text-xs text-[var(--cw-muted)]">No shared move numbers with enough games on both sides yet.</p>
                    )}
                  </>
                )
              })()}
            </>
          )}
        </div>
      )}
    </div>
  )
}

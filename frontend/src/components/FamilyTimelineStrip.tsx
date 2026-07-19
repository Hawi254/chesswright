import { useState } from 'react'
import Plot from 'react-plotly.js'
import { lineChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import TrendArrow from './TrendArrow'
import { useFamilyDeepDive } from '../hooks/useFamilyDeepDive'
import type { LedgerRow, StripPoint } from '../hooks/useEvolutionSummary'

const STATUS_TEXT: Record<LedgerRow['status'], string> = {
  adopted: '🆕 Adopted',
  dropped: '✂️ Dropped',
  rising: '📈 Rising',
  fading: '📉 Fading',
  stable: 'Stable',
}

function pctArrow(early: number | null, late: number | null): string {
  const fmt = (v: number | null) => (v === null ? '—' : `${v.toFixed(0)}%`)
  return `${fmt(early)} → ${fmt(late)}`
}

function statusLabel(row: LedgerRow): string {
  const base = STATUS_TEXT[row.status]
  if (row.status === 'adopted') return `${base} (${row.adopted_label})`
  if (row.status === 'dropped') return `${base} (${row.dropped_label})`
  return base
}

export default function FamilyTimelineStrip({
  row,
  stripPoints,
  familyColor,
  color,
  timeControl,
}: {
  row: LedgerRow
  stripPoints: StripPoint[]
  familyColor: string
  color: 'white' | 'black'
  timeControl: string | null
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [hasOpened, setHasOpened] = useState(false)
  const { deepDive, loading, error } = useFamilyDeepDive(hasOpened ? row.family : null, color, timeControl)

  function handleToggle() {
    setHasOpened(true)
    setIsOpen((v) => !v)
  }

  const sortedPoints = [...stripPoints].sort((a, b) => a.period - b.period)
  const maxShare = Math.max(...sortedPoints.map((p) => p.share), 1)

  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)]">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={handleToggle}
        className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left"
      >
        <div className="w-40 shrink-0">
          <span className="block font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]">
            {row.family}
          </span>
          <span className="block text-[10px] text-[var(--cw-muted)]">{statusLabel(row)}</span>
        </div>

        <div
          className="grid flex-1 gap-px"
          style={{ gridTemplateColumns: `repeat(${sortedPoints.length}, minmax(4px, 1fr))` }}
        >
          {sortedPoints.map((point) => (
            <div
              key={point.period}
              title={`${point.label}: ${point.share.toFixed(1)}%`}
              className="h-4 rounded-sm"
              style={{ backgroundColor: familyColor, opacity: point.share / maxShare }}
            />
          ))}
        </div>

        <div className="w-32 shrink-0 text-right text-[10px] text-[var(--cw-muted)]">
          {pctArrow(row.share_early, row.share_late)}
        </div>
        <div className="w-20 shrink-0 text-right">
          <TrendArrow
            delta={row.win_early !== null && row.win_late !== null ? row.win_late - row.win_early : null}
            goodDirection="up"
            unit="%"
          />
        </div>
        <div className="w-20 shrink-0 text-right text-[10px] text-[var(--cw-muted)]">
          {row.n_games_total.toLocaleString()} games
        </div>
        <span aria-hidden="true">{isOpen ? '−' : '+'}</span>
      </button>

      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="grid grid-cols-1 gap-4 px-4 pb-4 sm:grid-cols-2">
            {loading && <p className="text-xs text-[var(--cw-muted)]">Loading…</p>}
            {!loading && error && (
              <p className="text-xs text-negative">Couldn&apos;t load this opening&apos;s trend.</p>
            )}
            {hasOpened && !loading && !error && deepDive && (
              <>
                <div>
                  {deepDive.trend.length < 2 ? (
                    <p className="text-xs text-[var(--cw-muted)]">
                      Not enough games per quarter for a win-rate trend.
                    </p>
                  ) : (
                    <Plot
                      {...lineChart(deepDive.trend, 'label', 'win_pct', THEME.positive, {
                        height: 260, xTitle: 'Quarter', yTitle: 'Win rate (%)',
                      })}
                      config={{ displayModeBar: false }}
                      style={{ width: '100%' }}
                    />
                  )}
                </div>
                <div>
                  {deepDive.acpl.length < 2 ? (
                    <p className="text-xs text-[var(--cw-muted)]">
                      Not enough analyzed moves for an accuracy trend.
                    </p>
                  ) : (
                    <>
                      <Plot
                        {...lineChart(deepDive.acpl, 'label', 'acpl', THEME.accentGold, {
                          height: 260, xTitle: 'Quarter', yTitle: 'Avg centipawn loss',
                        })}
                        config={{ displayModeBar: false }}
                        style={{ width: '100%' }}
                      />
                      {(() => {
                        const coverages = deepDive.acpl.map((p) => p.coverage_pct)
                        const min = Math.min(...coverages)
                        const max = Math.max(...coverages)
                        return max >= 2 * Math.max(min, 0.1) ? (
                          <p className="mt-1 text-[10px] text-[var(--cw-muted)]">
                            ⚠️ These quarters aren&apos;t equally analyzed ({min.toFixed(1)}%–{max.toFixed(1)}%
                            coverage) — a shift here can mean &quot;this quarter finally got analyzed&quot; rather
                            than a real accuracy change.
                          </p>
                        ) : null
                      })()}
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

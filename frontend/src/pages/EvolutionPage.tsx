import { useState } from 'react'
import { useEvolutionSummary } from '../hooks/useEvolutionSummary'
import CompositionChart from '../components/CompositionChart'
import FamilyTimelineStrip from '../components/FamilyTimelineStrip'
import { THEME } from '../lib/theme'

const TIME_CONTROL_OPTIONS = [
  { value: 'all', label: 'All time controls' },
  { value: 'bullet', label: 'Bullet' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'classical', label: 'Classical' },
]

const toggleClass = (active: boolean) =>
  `rounded-md border px-3 py-1 font-condensed text-xs uppercase tracking-[0.08em] ${
    active
      ? 'border-[var(--cw-copper)] text-[var(--cw-copper)]'
      : 'border-[var(--cw-line)] text-[var(--cw-muted)]'
  }`

export default function EvolutionPage() {
  const [color, setColor] = useState<'white' | 'black'>('white')
  const [timeControl, setTimeControl] = useState<string | null>(null)
  const [grouping, setGrouping] = useState<'family' | 'eco'>('family')

  const { summary, loading, error } = useEvolutionSummary(color, timeControl, grouping)

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Repertoire Evolution</h1>
      <p className="mt-1 text-sm text-[var(--cw-muted)]">
        How your opening repertoire changed across your career — what you adopted, what you
        dropped, and whether each change paid off.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-6">
        <div className="flex gap-2">
          <button type="button" onClick={() => setColor('white')} className={toggleClass(color === 'white')}>
            ⬜ White
          </button>
          <button type="button" onClick={() => setColor('black')} className={toggleClass(color === 'black')}>
            ⬛ Black
          </button>
        </div>
        <label className="text-xs text-[var(--cw-muted)]">
          Time control
          <select
            value={timeControl ?? 'all'}
            onChange={(e) => setTimeControl(e.target.value === 'all' ? null : e.target.value)}
            className="mt-1 block w-40 rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-2 py-1 text-[var(--cw-text)]"
          >
            {TIME_CONTROL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-[var(--cw-muted)]">
          Group openings by
          <select
            value={grouping}
            onChange={(e) => setGrouping(e.target.value as 'family' | 'eco')}
            className="mt-1 block w-48 rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-2 py-1 text-[var(--cw-text)]"
          >
            <option value="family">Opening family</option>
            <option value="eco">ECO section (A–E)</option>
          </select>
        </label>
      </div>

      {loading && <p className="mt-6 text-[var(--cw-muted)]">Loading…</p>}
      {!loading && (error || !summary) && (
        <p className="mt-6 text-negative">
          Couldn&apos;t load your Repertoire Evolution data. Confirm the Chesswright API server is running.
        </p>
      )}
      {!loading && !error && summary && summary.totalGames === 0 && (
        <p className="mt-6 text-[var(--cw-muted)]">No games here yet — sync your games first, then come back.</p>
      )}
      {!loading && !error && summary && summary.totalGames > 0 && summary.nPeriods < 2 && (
        <p className="mt-6 text-[var(--cw-muted)]">
          All these games fall in a single quarter — play across a longer stretch to see your repertoire evolve.
        </p>
      )}
      {!loading && !error && summary && summary.totalGames > 0 && summary.nPeriods >= 2 && (
        <>
          <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
            <h2 className="font-condensed text-sm uppercase tracking-[0.08em] text-[var(--cw-muted)]">
              Where your games went
            </h2>
            <CompositionChart shares={summary.composition.shares} top={summary.composition.top} />
          </div>

          <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
            <h2 className="font-condensed text-sm uppercase tracking-[0.08em] text-[var(--cw-muted)]">
              Adopted, dropped, rising, fading
            </h2>
            {summary.ledger.length === 0 ? (
              <p className="mt-3 text-xs text-[var(--cw-muted)]">
                No opening here clears the ledger&apos;s floors yet.
              </p>
            ) : (
              <div className="mt-3 flex flex-col gap-2">
                {summary.ledger.map((row) => {
                  const rank = summary.composition.top.indexOf(row.family)
                  const familyColor = rank >= 0
                    ? THEME.categoricalSeries[rank % THEME.categoricalSeries.length]
                    : THEME.categoricalOther
                  return (
                    <FamilyTimelineStrip
                      key={row.family}
                      row={row}
                      stripPoints={summary.strips.filter((p) => p.family === row.family)}
                      familyColor={familyColor}
                      color={color}
                      timeControl={timeControl}
                    />
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import Slider from './ui/Slider'
import PositionInspector from './PositionInspector'
import { useRepertoireHoles } from '../hooks/useRepertoireHoles'
import type { RepertoireHoleRow } from '../hooks/useRepertoireHoles'

export default function RepertoireHolesSection() {
  const [minAppearances, setMinAppearances] = useState(5)
  const [topN, setTopN] = useState(20)
  const { holes, loading, error } = useRepertoireHoles(minAppearances, topN)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [flip, setFlip] = useState(false)

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!holes || holes.length === 0) return
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev === null ? 0 : Math.min(holes.length - 1, prev + 1)))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev === null ? 0 : Math.max(0, prev - 1)))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [holes])

  if (loading || error || !holes) return null

  const maxHoleScore = Math.max(...holes.map((h) => h.hole_score ?? 0), 1)
  const selected: RepertoireHoleRow | null = selectedIndex !== null ? holes[selectedIndex] : null
  const topHole = holes[0]

  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">
        A &quot;hole&quot; is a position you&apos;ve reached multiple times but keep playing
        differently — ranked by inconsistency × average CPL. Only analyzed games are included.
        Use ↑/↓ to step through rows.
      </p>
      <div className="mt-3 flex flex-wrap gap-4">
        <div className="w-48">
          <Slider id="holes-min-appearances" label="Min times reached" min={3} max={20} value={minAppearances} onChange={setMinAppearances} />
        </div>
        <div className="w-48">
          <Slider id="holes-top-n" label="Show top N" min={5} max={50} value={topN} onChange={setTopN} />
        </div>
      </div>
      {holes.length === 0 ? (
        <p className="mt-3 text-xs text-[var(--cw-muted)]">Not enough repeated positions yet.</p>
      ) : (
        <>
          <p className="mt-3 text-xs text-[var(--cw-muted)]">
            Biggest hole: move {topHole.approx_move_number} ({topHole.opening ?? 'unknown opening'}) —
            reached {topHole.n_games}× with {topHole.n_distinct_moves} different moves and avg{' '}
            {topHole.avg_cpl === null ? '--' : topHole.avg_cpl.toFixed(0)} CPL.
          </p>
          <div className="mt-3 grid grid-cols-[minmax(280px,1fr)_minmax(320px,480px)] gap-4">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                  <th scope="col" className="py-2 pr-3">At move</th>
                  <th scope="col" className="py-2 pr-3">Opening</th>
                  <th scope="col" className="py-2 pr-3">Usual move</th>
                  <th scope="col" className="py-2 pr-3">Times reached</th>
                  <th scope="col" className="py-2 pr-3">Variations tried</th>
                  <th scope="col" className="py-2 pr-3">Avg CPL</th>
                  <th scope="col" className="py-2">Hole score</th>
                </tr>
              </thead>
              <tbody>
                {holes.map((h, i) => (
                  <tr
                    key={h.fen_before}
                    onClick={() => setSelectedIndex(i)}
                    className={`cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)] ${i === selectedIndex ? 'bg-[var(--cw-panel)]' : ''}`}
                  >
                    <td className="py-2 pr-3">{h.approx_move_number}</td>
                    <td className="py-2 pr-3">{h.opening ?? '—'}</td>
                    <td className="py-2 pr-3">{h.most_played_san}</td>
                    <td className="py-2 pr-3">{h.n_games}</td>
                    <td className="py-2 pr-3">{h.n_distinct_moves}</td>
                    <td className="py-2 pr-3">{h.avg_cpl === null ? '--' : h.avg_cpl.toFixed(1)}</td>
                    <td className="py-2">
                      {h.hole_score === null ? (
                        '--'
                      ) : (
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--cw-line)]">
                          <div className="h-full bg-[var(--cw-copper)]" style={{ width: `${(h.hole_score / maxHoleScore) * 100}%` }} />
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <PositionInspector
              fen={selected?.fen_before ?? null}
              playerSan={selected?.most_played_san}
              flip={flip}
              onFlipToggle={() => setFlip((prev) => !prev)}
            />
          </div>
        </>
      )}
    </div>
  )
}

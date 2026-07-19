import { useEffect, useState } from 'react'
import Slider from './ui/Slider'
import PositionInspector from './PositionInspector'
import { useRepeatedPositions } from '../hooks/useRepeatedPositions'
import { usePositionFen } from '../hooks/usePositionFen'

export default function RepeatedPositionsSection() {
  const [topN, setTopN] = useState(20)
  const { positions, loading, error } = useRepeatedPositions(topN)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [flip, setFlip] = useState(false)

  const selected = selectedIndex !== null && positions ? positions[selectedIndex] : null
  const { fen } = usePositionFen(selected?.ply ?? null, selected?.zobrist_hash ?? null)

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!positions || positions.length === 0) return
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev === null ? 0 : Math.min(positions.length - 1, prev + 1)))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev === null ? 0 : Math.max(0, prev - 1)))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [positions])

  if (loading || error || !positions) return null

  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">
        Positions you&apos;ve reached more than once (matched by exact board state, not just
        opening name) — click a row to view the board. Use ↑/↓ to step through rows.
      </p>
      <div className="mt-3 w-48">
        <Slider id="repeated-top-n" label="Show top N" min={5} max={50} value={topN} onChange={setTopN} />
      </div>
      <div className="mt-3 grid grid-cols-[minmax(280px,1fr)_minmax(320px,480px)] gap-4">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              <th scope="col" className="py-2 pr-3">Move #</th>
              <th scope="col" className="py-2 pr-3">Times reached</th>
              <th scope="col" className="py-2 pr-3">Win %</th>
              <th scope="col" className="py-2 pr-3">Draw %</th>
              <th scope="col" className="py-2 pr-3">Loss %</th>
              <th scope="col" className="py-2">Most common opening</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => (
              <tr
                key={`${p.ply}|${p.zobrist_hash}`}
                onClick={() => setSelectedIndex(i)}
                className={`cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)] ${i === selectedIndex ? 'bg-[var(--cw-panel)]' : ''}`}
              >
                <td className="py-2 pr-3">{Math.floor((p.ply + 1) / 2)}</td>
                <td className="py-2 pr-3">{p.n_games}</td>
                <td className="py-2 pr-3">{p.win_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{p.draw_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{p.loss_pct.toFixed(1)}</td>
                <td className="py-2">{p.common_opening ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <PositionInspector fen={fen} flip={flip} onFlipToggle={() => setFlip((prev) => !prev)} />
      </div>
    </div>
  )
}

import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import Chessboard from './Chessboard'
import type { HighlightCategory, HighlightMoment } from '../hooks/useTacticalHighlightsReel'

const CATEGORY_LABELS: Record<HighlightCategory, string> = {
  brilliant: 'Brilliant',
  puzzle_conversion: 'Puzzle conversion',
  best_move_streak: 'Best-move streak',
  blown_mate: 'Blown mate',
  great_escape: 'Great escape',
}

// Positive framing for the 2 categories where zero is good news (no
// forced mates lost, no pieces hung and survived only by luck); neutral
// for the other 3, where zero just means "none found yet."
const EMPTY_COPY: Record<HighlightCategory, string> = {
  brilliant: 'No brilliant sacrifices found yet in your analyzed games.',
  puzzle_conversion: "No opponent-blunder conversions found yet in your analyzed games.",
  best_move_streak: 'No best-move streaks of 3 or more found yet in your analyzed games.',
  blown_mate: 'No forced mates were ever let slip — every mate you found, you delivered.',
  great_escape: 'No must-escape moments here — no hung pieces that could have cost you the game.',
}

export default function HighlightReel({
  moments,
  activeCategory,
  activeIndex,
  onIndexChange,
}: {
  moments: HighlightMoment[]
  activeCategory: 'all' | HighlightCategory
  activeIndex: number
  onIndexChange: (index: number) => void
}) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'ArrowLeft' && activeIndex > 0) {
        e.preventDefault()
        onIndexChange(activeIndex - 1)
      } else if (e.key === 'ArrowRight' && activeIndex < moments.length - 1) {
        e.preventDefault()
        onIndexChange(activeIndex + 1)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeIndex, moments.length, onIndexChange])

  if (moments.length === 0) {
    return (
      <p className="mt-6 text-sm text-[var(--cw-muted)]">
        {activeCategory === 'all' ? EMPTY_COPY.brilliant : EMPTY_COPY[activeCategory]}
      </p>
    )
  }

  const moment = moments[Math.min(activeIndex, moments.length - 1)]
  const arrows = moment.lastmove_from && moment.lastmove_to
    ? [{ from: moment.lastmove_from, to: moment.lastmove_to, color: 'var(--color-accent-gold)' }]
    : []

  return (
    <div className="mt-6">
      <div className="grid grid-cols-[minmax(240px,320px)_1fr] gap-4">
        <div style={{ width: '100%', maxWidth: '320px' }}>
          <Chessboard
            fen={moment.fen ?? undefined}
            orientation={moment.player_color === 'black' ? 'black' : 'white'}
            lastmoveFrom={null}
            lastmoveTo={null}
            arrows={arrows}
            interactive={false}
          />
        </div>
        <div className="text-sm text-[var(--cw-text)]">
          <div className="font-condensed text-[10px] uppercase tracking-[0.08em] text-[var(--cw-copper)]">
            {CATEGORY_LABELS[moment.category]}
          </div>
          <p className="mt-2 font-mono text-xs">{moment.san}</p>
          <p className="mt-2">{moment.caption}</p>
          <p className="mt-2 font-condensed text-xs text-[var(--cw-copper)]">{moment.magnitude_label}</p>
          <p className="mt-2 text-xs text-[var(--cw-muted)]">
            vs. {moment.opponent_name} · {moment.utc_date} · <span className="capitalize">{moment.outcome_for_player}</span>
          </p>
          <Link
            to={`/tactical-highlights/${moment.game_id}`}
            className="mt-3 inline-block text-xs text-[var(--cw-copper)] hover:underline"
          >
            View full game →
          </Link>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          disabled={activeIndex === 0}
          onClick={() => onIndexChange(activeIndex - 1)}
          className="rounded border border-[var(--cw-line)] px-2 py-1 font-condensed text-xs text-[var(--cw-text)] disabled:opacity-40"
        >
          Prev
        </button>
        <span className="font-mono text-xs text-[var(--cw-muted)]">
          {activeIndex + 1} / {moments.length}
        </span>
        <button
          type="button"
          disabled={activeIndex === moments.length - 1}
          onClick={() => onIndexChange(activeIndex + 1)}
          className="rounded border border-[var(--cw-line)] px-2 py-1 font-condensed text-xs text-[var(--cw-text)] disabled:opacity-40"
        >
          Next
        </button>
        <div className="flex gap-1">
          {moments.map((m, i) => (
            <button
              key={m.game_id + m.category + m.move_number}
              type="button"
              aria-label={`Go to moment ${i + 1}`}
              onClick={() => onIndexChange(i)}
              className={`h-1.5 w-1.5 rounded-full ${
                i === activeIndex ? 'bg-[var(--cw-copper)]' : 'bg-[var(--cw-line)]'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

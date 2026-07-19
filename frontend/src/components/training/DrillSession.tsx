import { useState } from 'react'
import { Chess } from 'chess.js'
import Chessboard from '../Chessboard'
import type { ChessMoveResult } from '../Chessboard'
import { useReviewSession, type SrsCard } from '../../hooks/useReviewSession'

// Mirrors chesswright_pro/srs_drills.py's _moves_match(): compares
// UCI (from-square + to-square [+promotion]), not the SAN string, so
// check-symbol/capture-notation differences never cause a false mismatch.
function bestMoveUci(fen: string, bestMoveSan: string): string | null {
  try {
    const probe = new Chess(fen)
    const move = probe.move(bestMoveSan)
    if (!move) return null
    return move.from + move.to + (move.promotion ?? '')
  } catch {
    return null
  }
}

export default function DrillSession({
  dueCount, onSessionChange,
}: { dueCount: number; onSessionChange: () => void }) {
  const session = useReviewSession()
  const [revealed, setRevealed] = useState(false)
  const [attempt, setAttempt] = useState<ChessMoveResult | null>(null)

  const active = session.queue !== null && session.idx < session.queue.length
  const complete = session.queue !== null && session.queue.length > 0 && session.idx >= session.queue.length

  function handleStart() {
    session.start().then(onSessionChange)
  }

  function handleMove(move: ChessMoveResult) {
    setAttempt(move)
    setRevealed(true)
  }

  function handleRate(card: SrsCard, rating: number) {
    session.rate(card.id, rating).then(() => {
      setRevealed(false)
      setAttempt(null)
      onSessionChange()
    })
  }

  function handleSkip(card: SrsCard) {
    session.skip(card.id).then(() => {
      setRevealed(false)
      setAttempt(null)
      onSessionChange()
    })
  }

  if (complete) {
    const again = session.results.filter((r) => r === 0).length
    const hard = session.results.filter((r) => r === 1).length
    const good = session.results.filter((r) => r === 2).length
    const easy = session.results.filter((r) => r === 3).length
    return (
      <div>
        <p className="text-sm text-[var(--cw-text)]">
          Session complete — {session.results.length} card{session.results.length === 1 ? '' : 's'} reviewed.
        </p>
        <p className="mt-1 text-xs text-[var(--cw-muted)]">
          Again {again} · Hard {hard} · Good {good} · Easy {easy}
        </p>
        <button type="button" onClick={() => { session.reset(); onSessionChange() }}
          className="mt-3 rounded border border-[var(--cw-copper)] px-3 py-1.5 text-xs text-[var(--cw-copper)]">
          Back to queue
        </button>
      </div>
    )
  }

  if (!active) {
    return (
      <div>
        {dueCount === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">
            Nothing due today. Come back tomorrow, or add more cards from Build Set.
          </p>
        ) : (
          <button type="button" onClick={handleStart}
            className="rounded border border-[var(--cw-copper)] bg-[var(--cw-copper)]/10 px-4 py-2 text-sm text-[var(--cw-copper)]">
            Start session ({dueCount} cards)
          </button>
        )}
      </div>
    )
  }

  const card = session.queue![session.idx]
  const bestUci = bestMoveUci(card.fen, card.best_move_san)
  const isCorrect = revealed && attempt ? attempt.uci === bestUci : null
  const flipped = card.fen.split(' ')[1] === 'b'

  const arrows =
    revealed && bestUci
      ? [
          { from: bestUci.slice(0, 2), to: bestUci.slice(2, 4), color: '#15781B' },
          ...(attempt && attempt.uci !== bestUci
            ? [{ from: attempt.uci.slice(0, 2), to: attempt.uci.slice(2, 4), color: '#c0392b' }]
            : []),
        ]
      : []

  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">
        Card {session.idx + 1} of {session.queue!.length}
      </p>
      {card.context && <p className="mt-1 text-xs text-[var(--cw-muted)]">{card.context}</p>}
      <div className="mt-3 max-w-[420px]">
        <Chessboard
          fen={card.fen}
          orientation={flipped ? 'black' : 'white'}
          lastmoveFrom={null}
          lastmoveTo={null}
          arrows={arrows}
          interactive={!revealed}
          onMove={handleMove}
        />
      </div>
      {!revealed ? (
        <div className="mt-3 flex gap-3">
          <button type="button" onClick={() => setRevealed(true)}
            className="rounded border border-[var(--cw-line)] px-3 py-1.5 text-xs text-[var(--cw-text)]">
            Show answer
          </button>
          <button type="button" onClick={() => handleSkip(card)}
            className="rounded border border-[var(--cw-line)] px-3 py-1.5 text-xs text-[var(--cw-muted)]">
            Skip
          </button>
        </div>
      ) : (
        <div className="mt-3">
          <p className="text-xs text-[var(--cw-text)]">
            {attempt
              ? isCorrect
                ? `Correct! You played ${attempt.san}.`
                : `You played ${attempt.san} — best was ${card.best_move_san}.`
              : `Best move: ${card.best_move_san}.`}
          </p>
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => handleRate(card, 0)} className="rounded border border-[var(--cw-line)] px-3 py-1.5 text-xs">Again</button>
            <button type="button" onClick={() => handleRate(card, 1)} className="rounded border border-[var(--cw-line)] px-3 py-1.5 text-xs">Hard</button>
            <button type="button" onClick={() => handleRate(card, 2)} className="rounded border border-[var(--cw-copper)] bg-[var(--cw-copper)]/10 px-3 py-1.5 text-xs text-[var(--cw-copper)]">Good</button>
            <button type="button" onClick={() => handleRate(card, 3)} className="rounded border border-[var(--cw-line)] px-3 py-1.5 text-xs">Easy</button>
          </div>
        </div>
      )}
    </div>
  )
}

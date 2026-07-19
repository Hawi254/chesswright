import { useEffect } from 'react'
import { Chess } from 'chess.js'
import Chessboard from './Chessboard'
import { useAnalysePosition } from '../hooks/useAnalysePosition'

function formatEval(evalCp: number | null, evalMate: number | null): string {
  if (evalMate !== null) return evalMate > 0 ? `M${evalMate}` : `−M${Math.abs(evalMate)}`
  if (evalCp !== null) return evalCp >= 0 ? `+${(evalCp / 100).toFixed(2)}` : (evalCp / 100).toFixed(2)
  return '—'
}

// Ported from dashboard/chess_display.py's pv_str -- reconstructs move-
// number notation ('1. Nf3 d5 2. d4') client-side via chess.js, since
// useAnalysePosition's `pv` is a plain SAN list with no move numbers.
function formatPv(fen: string, sanMoves: string[], maxMoves = 6): string | null {
  const board = new Chess(fen)
  const parts: string[] = []
  for (const san of sanMoves.slice(0, maxMoves)) {
    let move
    try {
      const whiteToMove = board.turn() === 'w'
      const fullmoveNumber = board.moveNumber()
      if (whiteToMove) parts.push(`${fullmoveNumber}. ${san}`)
      else if (parts.length === 0) parts.push(`${fullmoveNumber}… ${san}`)
      else parts.push(san)
      move = board.move(san)
    } catch {
      break
    }
    if (!move) break
  }
  return parts.length > 0 ? parts.join(' ') : null
}

function resolveArrow(fen: string, san: string): { from: string; to: string } | null {
  try {
    const game = new Chess(fen)
    const move = game.moves({ verbose: true }).find((m) => m.san === san)
    return move ? { from: move.from, to: move.to } : null
  } catch {
    return null
  }
}

export default function PositionInspector({
  fen,
  playerSan,
  flip,
  onFlipToggle,
}: {
  fen: string | null
  playerSan?: string
  flip: boolean
  onFlipToggle: () => void
}) {
  const { analyse, result, resultFen, status, loading } = useAnalysePosition()

  useEffect(() => {
    if (fen) analyse(fen)
    // analyse isn't memoized by useAnalysePosition -- only fen should retrigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fen])

  if (!fen) return null

  const hasFreshResult = status === 'ok' && result !== null && resultFen === fen
  const engineSan = hasFreshResult ? result!.best_move_san : null
  const sameMove = Boolean(engineSan && playerSan && engineSan === playerSan)

  const arrows: Array<{ from: string; to: string; color: string }> = []
  if (playerSan) {
    const playerArrow = resolveArrow(fen, playerSan)
    if (playerArrow) arrows.push({ ...playerArrow, color: 'var(--color-accent-gold)' })
  }
  // Engine arrow draws whenever there's no playerSan to compare against
  // (Repeated Positions) OR the engine's move differs from the player's
  // usual move (Repertoire Holes) -- sameMove is always false when
  // playerSan is falsy, so this one guard covers both cases.
  if (hasFreshResult && result!.best_move_from && result!.best_move_to && !sameMove) {
    arrows.push({ from: result!.best_move_from, to: result!.best_move_to, color: 'var(--color-positive)' })
  }

  return (
    <div className="grid grid-cols-[minmax(240px,360px)_1fr] gap-4">
      <div>
        <Chessboard fen={fen} orientation={flip ? 'black' : 'white'} lastmoveFrom={null} lastmoveTo={null}
                    arrows={arrows} interactive={false} />
        <button type="button" onClick={onFlipToggle}
                className="mt-2 rounded border border-[var(--cw-line)] px-2 py-1 font-condensed text-[10px] uppercase tracking-[0.08em] text-[var(--cw-muted)] hover:text-[var(--cw-text)]">
          Flip board
        </button>
      </div>
      <div className="text-xs text-[var(--cw-text)]">
        {playerSan && (
          <p>
            Your usual move: <strong>{playerSan}</strong>
            {sameMove ? ' ✓ engine agrees' : ' (gold arrow)'}
          </p>
        )}
        {loading && <p className="text-[var(--cw-muted)]">Analysing…</p>}
        {status === 'no_engine' && <p className="text-negative">Stockfish not found — configure it in Settings.</p>}
        {status === 'batch_running' && <p className="text-[var(--cw-muted)]">Batch analysis running — live engine paused.</p>}
        {status === 'analysis_failed' && <p className="text-negative">This position couldn&apos;t be analysed.</p>}
        {hasFreshResult && result && (
          <>
            <p className="mt-2">Eval: <strong>{formatEval(result.eval_cp, result.eval_mate)}</strong></p>
            {result.best_move_san && (!playerSan || !sameMove) && (
              <p>Engine best: <strong>{result.best_move_san}</strong>{playerSan ? ' (green arrow)' : ''}</p>
            )}
            {result.pv.length > 0 && (
              <p className="mt-1 text-[var(--cw-muted)]">
                Line: {formatPv(fen, result.pv)}{result.depth !== null ? ` (depth ${result.depth})` : ''}
              </p>
            )}
            {result.source === 'live' && <p className="mt-1 text-[var(--cw-muted)]">Live engine result (not from batch).</p>}
            {result.source === 'lichess_cloud' && <p className="mt-1 text-[var(--cw-muted)]">From Lichess&apos;s cloud evaluation database.</p>}
          </>
        )}
      </div>
    </div>
  )
}

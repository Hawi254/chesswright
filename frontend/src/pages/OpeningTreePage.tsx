import { useMemo, useState } from 'react'
import { Chess } from 'chess.js'
import Chessboard from '../components/Chessboard'
import OpeningTreeControls from '../components/OpeningTreeControls'
import OpeningTreeIcicle from '../components/OpeningTreeIcicle'
import OpeningMoveTable from '../components/OpeningMoveTable'
import PositionTimelinePanel from '../components/PositionTimelinePanel'
import RepertoireChangesList from '../components/RepertoireChangesList'
import OpeningTreeFlipDrawer from '../components/OpeningTreeFlipDrawer'
import { useProStatus } from '../hooks/useProStatus'
import { useOpeningTreeMap } from '../hooks/useOpeningTreeMap'
import { useOpeningTreeMoves } from '../hooks/useOpeningTreeMoves'
import { useAddSrsCard } from '../hooks/useAddSrsCard'
import type { OpeningChange } from '../hooks/useOpeningTreeChanges'

const INITIAL_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

function ProUpsell() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-[var(--cw-text)]">Opening Tree</h1>
      <p className="mt-2 text-xs text-[var(--cw-text)]">
        <strong>Opening Tree</strong> is a Chesswright Pro feature. Explore your repertoire as a live,
        linked map: jump straight to any opening, drill through your actual games move by move with
        win rates and accuracy at every branch, spot exactly where your repertoire has changed over
        time, and push weak positions straight into your SRS queue. Upgrade to Pro to unlock this
        feature. &rarr;{' '}
        <a href="https://chesswright.gumroad.com" target="_blank" rel="noreferrer" className="text-[var(--cw-copper)]">
          chesswright.gumroad.com
        </a>
      </p>
    </div>
  )
}

function replayPath(path: string[]): string {
  const board = new Chess()
  for (const san of path) {
    try { board.move(san) } catch { break }
  }
  return board.fen()
}

export default function OpeningTreePage() {
  const proStatus = useProStatus()
  const [color, setColor] = useState<'w' | 'b'>('w')
  const [minGames, setMinGames] = useState(3)
  const [path, setPath] = useState<string[]>([])
  const [openFlip, setOpenFlip] = useState<OpeningChange | null>(null)

  const currentFen = useMemo(() => replayPath(path), [path])
  const ply = path.length + 1
  const playerTurn = useMemo(() => {
    const board = new Chess(currentFen)
    return (color === 'w' && board.turn() === 'w') || (color === 'b' && board.turn() === 'b')
  }, [currentFen, color])

  // Both hooks are called unconditionally (Rules of Hooks) even though
  // the page renders nothing but the upsell until Pro is confirmed
  // active -- gated here via `enabled`/a null fen, found live 2026-07-16
  // as three 403s firing against /api/opening-tree/* on every load of
  // the non-Pro upsell screen.
  const { map, loading: mapLoading } = useOpeningTreeMap(color, minGames, proStatus.active)
  const { moves, loading: movesLoading } = useOpeningTreeMoves(
    proStatus.active ? currentFen : null, ply, color, minGames)
  const { addCard, status: addCardStatus } = useAddSrsCard()

  if (proStatus.loading) return null
  if (!proStatus.active) return <ProUpsell />

  function playMove(san: string) {
    setPath([...path, san])
  }

  // "target: <top move>" per the design spec's layout -- the current
  // position's most-played move for the player, i.e. the move table's
  // first (highest-n_games) row. Not shown when it's the opponent's turn
  // (there is no "player's move" to target) or the table is empty.
  const topMove = playerTurn && moves.length > 0 ? moves[0] : null

  return (
    <div className="flex flex-col">
      <OpeningTreeControls color={color} onColorChange={setColor} minGames={minGames}
        onMinGamesChange={setMinGames} onJumpToPath={setPath} />

      <div className="grid grid-cols-2 gap-4 p-3">
        <div>
          {path.length > 0 && (
            <div className="mb-2 flex gap-2 text-xs">
              <button type="button" onClick={() => setPath(path.slice(0, -1))}
                className="text-[var(--cw-muted)] hover:text-[var(--cw-text)]">← Back</button>
              <button type="button" onClick={() => setPath([])}
                className="text-[var(--cw-muted)] hover:text-[var(--cw-text)]">⌂ Reset</button>
            </div>
          )}
          <Chessboard fen={currentFen} orientation={color === 'b' ? 'black' : 'white'}
            lastmoveFrom={null} lastmoveTo={null} interactive
            onMove={(move) => playMove(move.san)} />
        </div>
        <div>
          {mapLoading || !map ? (
            <p className="text-xs text-[var(--cw-muted)]">Loading overview…</p>
          ) : (
            <OpeningTreeIcicle map={map} onNodeClick={setPath} />
          )}
        </div>
      </div>

      {movesLoading ? (
        <p className="p-3 text-xs text-[var(--cw-muted)]">Loading…</p>
      ) : (
        <OpeningMoveTable moves={moves} playerTurn={playerTurn} onPlayMove={playMove} />
      )}

      <PositionTimelinePanel fen={currentFen} color={color} />

      {topMove && (
        <button type="button"
          onClick={() => addCard(currentFen, topMove.san, path.join(' '))}
          disabled={addCardStatus === 'saving'}
          className="m-3 self-start rounded border border-[var(--cw-line)] px-2 py-1 text-xs text-[var(--cw-text)]">
          {addCardStatus === 'ok' ? 'Added ✓' : `Add to SRS deck (${topMove.san})`}
        </button>
      )}

      <RepertoireChangesList color={color} minGames={minGames} onJumpToPath={setPath}
        onOpenFlip={setOpenFlip} />

      <OpeningTreeFlipDrawer change={openFlip} color={color} onClose={() => setOpenFlip(null)}
        onJumpToPath={setPath} />
    </div>
  )
}

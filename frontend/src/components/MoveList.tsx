import type { GameDetailMove } from '../hooks/useGameDetail'

function moveLabel(ply: number, san: string): string {
  const isWhite = ply % 2 === 1
  const moveNumber = Math.floor((ply + 1) / 2)
  return isWhite ? `${moveNumber}. ${san}` : san
}

export default function MoveList({
  moves,
  currentPly,
  onSelectPly,
}: {
  moves: GameDetailMove[]
  currentPly: number | null
  onSelectPly: (ply: number) => void
}) {
  if (moves.length === 0) {
    return <p className="text-xs text-[var(--cw-muted)]">No moves recorded for this game.</p>
  }

  return (
    <div className="max-h-[420px] overflow-y-auto font-mono text-xs text-[var(--cw-text)]">
      {moves.map((move) => (
        <button
          key={move.ply}
          type="button"
          onClick={() => onSelectPly(move.ply)}
          className={`mr-2 mb-1 rounded px-1.5 py-0.5 ${
            move.ply === currentPly
              ? 'bg-[var(--cw-copper)]/20 text-[var(--cw-copper)]'
              : 'hover:bg-[var(--cw-panel)]'
          }`}
        >
          {moveLabel(move.ply, move.san)}
        </button>
      ))}
    </div>
  )
}

import Chessboard from './Chessboard'
import type { OpeningChange } from '../hooks/useOpeningTreeChanges'

const INITIAL_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

export default function OpeningTreeFlipDrawer({
  change, color, onClose, onJumpToPath,
}: {
  change: OpeningChange | null
  color: 'w' | 'b'
  onClose: () => void
  onJumpToPath: (path: string[]) => void
}) {
  if (!change) return null

  return (
    <div className="fixed inset-y-0 right-0 w-96 border-l border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <button type="button" onClick={onClose} className="text-xs text-[var(--cw-muted)]">Close</button>
      <Chessboard fen={INITIAL_FEN} orientation={color === 'b' ? 'black' : 'white'}
        lastmoveFrom={null} lastmoveTo={null} interactive={false} />
      <p className="mt-2 text-xs text-[var(--cw-text)]">
        Was <strong>{change.before_san}</strong> ({change.before_win_pct}% win, {change.before_total} games) — now{' '}
        <strong>{change.after_san}</strong> ({change.after_win_pct}% win, {change.after_total} games)
      </p>
      {change.path === null ? (
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          No single verified move order reaches this position (transposition) — board preview only.
        </p>
      ) : (
        <button type="button"
          onClick={() => { onJumpToPath(change.path as string[]); onClose() }}
          className="mt-2 rounded border border-[var(--cw-line)] px-2 py-1 text-xs text-[var(--cw-text)]">
          Jump to this position
        </button>
      )}
    </div>
  )
}

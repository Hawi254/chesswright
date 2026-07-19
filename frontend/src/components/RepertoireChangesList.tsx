import { useOpeningTreeChanges, type OpeningChange } from '../hooks/useOpeningTreeChanges'

export default function RepertoireChangesList({
  color, minGames, onJumpToPath, onOpenFlip,
}: {
  color: 'w' | 'b'
  minGames: number
  onJumpToPath: (path: string[]) => void
  onOpenFlip: (change: OpeningChange) => void
}) {
  const { changes, loading } = useOpeningTreeChanges(color, minGames)

  if (loading) return <p className="p-3 text-xs text-[var(--cw-muted)]">Loading…</p>
  if (changes.length === 0) {
    return <p className="p-3 text-xs text-[var(--cw-muted)]">No repertoire changes found with these thresholds.</p>
  }

  return (
    <div className="divide-y divide-[var(--cw-line)]">
      {changes.map((change) => (
        <div key={`${change.zobrist_hash}-${change.ply}`}
          className="flex cursor-pointer items-center gap-3 p-2 text-xs text-[var(--cw-text)] hover:bg-[var(--cw-panel-2)]"
          onClick={() => onOpenFlip(change)}>
          <span>{change.before_san} ({change.before_win_pct}%)</span>
          <span>&rarr;</span>
          <span>{change.after_san} ({change.after_win_pct}%)</span>
          {change.path === null && (
            <span className="text-[var(--cw-muted)]">no single verified move order</span>
          )}
          <button type="button" disabled={change.path === null}
            className="ml-auto rounded border border-[var(--cw-line)] px-2 py-1 disabled:opacity-40"
            onClick={(e) => { e.stopPropagation(); if (change.path) onJumpToPath(change.path) }}>
            Jump here
          </button>
        </div>
      ))}
    </div>
  )
}

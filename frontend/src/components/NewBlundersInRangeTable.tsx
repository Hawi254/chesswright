import type { BatchImpactBlunder } from '../hooks/useBatchImpact'

export default function NewBlundersInRangeTable({
  blunders, onSelectGame,
}: {
  blunders: BatchImpactBlunder[]
  onSelectGame: (gameId: string) => void
}) {
  if (blunders.length === 0) return null
  return (
    <div className="mt-4">
      <h3 className="font-condensed text-sm font-bold text-[var(--cw-text)]">New blunders in this range</h3>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              <th scope="col" className="py-2 pr-3">Game</th>
              <th scope="col" className="py-2 pr-3">Ply</th>
              <th scope="col" className="py-2 pr-3">Move</th>
              <th scope="col" className="py-2 pr-3">CPL</th>
              <th scope="col" className="py-2">Motif</th>
            </tr>
          </thead>
          <tbody>
            {blunders.map((b, i) => (
              <tr
                key={`${b.gameId}-${b.ply}-${i}`}
                onClick={() => onSelectGame(b.gameId)}
                className="cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)]"
              >
                <td className="py-2 pr-3 font-mono">{b.gameId}</td>
                <td className="py-2 pr-3">{b.ply}</td>
                <td className="py-2 pr-3">{b.san}</td>
                <td className="py-2 pr-3">{b.cpl}</td>
                <td className="py-2">{b.motif ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

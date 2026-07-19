import type { PointsCostliestGame } from '../hooks/usePointsLedger'
import { POINTS_BUCKET_LABEL } from '../lib/pointsLabels'
import type { PointsBucketKey } from '../lib/pointsLabels'

export default function PointsCostliestTable({
  games,
  activeBucket,
  onClearBucket,
  onSelectGame,
}: {
  games: PointsCostliestGame[]
  activeBucket: PointsBucketKey | null
  onClearBucket: () => void
  onSelectGame: (gameId: string) => void
}) {
  if (games.length === 0) return null
  const rows = activeBucket ? games.filter((g) => g.bucket === activeBucket) : games

  return (
    <div className="mt-3">
      {activeBucket && (
        <button
          type="button"
          onClick={onClearBucket}
          className="mb-2 rounded px-2.5 py-1 font-condensed text-xs bg-[var(--cw-copper)]/20 text-[var(--cw-copper)] border border-[var(--cw-copper)]/50"
        >
          Showing: {POINTS_BUCKET_LABEL[activeBucket]} ✕
        </button>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              <th scope="col" className="py-2 pr-3">Date</th>
              <th scope="col" className="py-2 pr-3">Opponent</th>
              <th scope="col" className="py-2 pr-3">Result</th>
              <th scope="col" className="py-2 pr-3">Leak</th>
              <th scope="col" className="py-2 pr-3">Best chance</th>
              <th scope="col" className="py-2 pr-3">Points leaked</th>
              <th scope="col" className="py-2">Game</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((game) => (
              <tr
                key={game.game_id}
                onClick={() => onSelectGame(game.game_id)}
                className="cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)]"
              >
                <td className="py-2 pr-3 font-mono">{game.utc_date}</td>
                <td className="py-2 pr-3">{game.opponent_name}</td>
                <td className="py-2 pr-3 capitalize">{game.outcome_for_player}</td>
                <td className="py-2 pr-3">{POINTS_BUCKET_LABEL[game.bucket]}</td>
                <td className="py-2 pr-3">{(game.best_chance * 100).toFixed(0)}%</td>
                <td className="py-2 pr-3">{game.leaked.toFixed(2)}</td>
                <td className="py-2">
                  {game.url ? (
                    <a
                      href={game.url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-[var(--cw-copper)]"
                    >
                      View ↗
                    </a>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

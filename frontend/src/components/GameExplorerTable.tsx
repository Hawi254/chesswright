import type { ExplorerGame } from '../hooks/useGameExplorer'
import { activeChipsFor, BADGE_LEGEND, TONE_CLASSES } from '../lib/badges'

const COLOR_GLYPH: Record<'white' | 'black', string> = { white: '⚪', black: '⚫' }

export default function GameExplorerTable({
  games,
  showPlatform,
  onSelectGame,
}: {
  games: ExplorerGame[]
  showPlatform: boolean
  onSelectGame: (gameId: string) => void
}) {
  if (games.length === 0) return null

  const maxDrama = Math.max(...games.map((g) => g.drama_score), 1)
  const anyBadges = games.some((game) => activeChipsFor(game).length > 0)

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
            <th scope="col" className="py-2 pr-3">Date</th>
            {showPlatform && <th scope="col" className="py-2 pr-3">Platform</th>}
            <th scope="col" className="py-2 pr-3">Opponent</th>
            <th scope="col" className="py-2 pr-3">Color</th>
            <th scope="col" className="py-2 pr-3">Result</th>
            <th scope="col" className="py-2 pr-3">Time Control</th>
            <th scope="col" className="py-2 pr-3">Opening</th>
            <th scope="col" className="py-2 pr-3">Badges</th>
            <th scope="col" className="py-2 pr-3">Drama</th>
            <th scope="col" className="py-2">Game</th>
          </tr>
        </thead>
        <tbody>
          {games.map((game) => {
            const chips = activeChipsFor(game)
            return (
              <tr
                key={game.game_id}
                onClick={() => onSelectGame(game.game_id)}
                className="cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)]"
              >
                <td className="py-2 pr-3 font-mono">{game.utc_date}</td>
                {showPlatform && <td className="py-2 pr-3">{game.platform}</td>}
                <td className="py-2 pr-3">{game.opponent_name}</td>
                <td className="py-2 pr-3">{COLOR_GLYPH[game.player_color]}</td>
                <td className="py-2 pr-3 capitalize">{game.outcome_for_player}</td>
                <td className="py-2 pr-3">{game.time_control_category}</td>
                <td className="py-2 pr-3">{game.opening_family}</td>
                <td className="py-2 pr-3">
                  <div className="flex flex-wrap gap-1">
                    {chips.map((chip) => (
                      <span
                        key={chip.key}
                        className={`rounded px-1.5 py-0.5 font-condensed text-[9px] ${TONE_CLASSES[chip.tone]}`}
                      >
                        {chip.label}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-2 pr-3">
                  <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--cw-line)]">
                    <div
                      className="h-full bg-[var(--cw-copper)]"
                      style={{ width: `${(game.drama_score / maxDrama) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="py-2">
                  {game.lichess_url ? (
                    <a
                      href={game.lichess_url}
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
            )
          })}
        </tbody>
      </table>
      {anyBadges && <p className="mt-2 text-xs text-[var(--cw-muted)]">{BADGE_LEGEND}</p>}
    </div>
  )
}

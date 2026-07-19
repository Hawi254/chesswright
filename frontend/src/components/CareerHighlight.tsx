import type { CareerHighlightGame } from '../hooks/useCareerHighlight'
import { activeChipsFor, BADGE_LEGEND, TONE_CLASSES } from '../lib/badges'

export default function CareerHighlight({ games }: { games: CareerHighlightGame[] | null }) {
  if (games === null || games.length === 0) return null

  const anyBadges = games.some((game) => activeChipsFor(game).length > 0)

  const ORDINALS = ['No. 1', 'No. 2', 'No. 3']

  return (
    <div className="mt-6">
      <h2 className="font-condensed text-[11px] text-[var(--cw-text)]">Career highlights</h2>
      <div className="mt-2 flex gap-3">
        {games.map((game, i) => {
          const chips = activeChipsFor(game)
          return (
            <div
              key={game.game_id}
              className={`flex-1 rounded-md border bg-[var(--cw-panel)] p-3 ${
                i === 0
                  ? 'border-[var(--cw-copper)]/50 border-t-2'
                  : 'border-[var(--cw-line)]'
              }`}
            >
              <div className="font-mono text-[10px] tracking-[0.1em] text-[var(--cw-copper)]">
                {ORDINALS[i] ?? `No. ${i + 1}`}
              </div>
              {chips.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {chips.map((chip) => (
                    <span
                      key={chip.key}
                      className={`rounded px-1.5 py-0.5 font-condensed text-[9px] ${TONE_CLASSES[chip.tone]}`}
                    >
                      {chip.label}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-1.5 text-xs text-[var(--cw-text)]">
                vs. {game.opponent_name} on {game.utc_date} ({game.outcome_for_player})
              </p>
            </div>
          )
        })}
      </div>
      {anyBadges && <p className="mt-2 text-xs text-[var(--cw-muted)]">{BADGE_LEGEND}</p>}
    </div>
  )
}

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import GameExplorerTable from '../components/GameExplorerTable'
import { BADGE_CHIPS, type BadgeFlags } from '../lib/badges'
import { useGameExplorer } from '../hooks/useGameExplorer'
import type { ExplorerGame } from '../hooks/useGameExplorer'

const MAX_ROWS = 200

export default function GameExplorerPage() {
  const { games, loading, error } = useGameExplorer()
  const navigate = useNavigate()
  const [selectedBadges, setSelectedBadges] = useState<Array<keyof BadgeFlags>>([])
  const [opponentSearch, setOpponentSearch] = useState('')
  const [analyzedOnly, setAnalyzedOnly] = useState(false)

  const filtered = useMemo(() => {
    if (!games) return []
    let rows: ExplorerGame[] = games
    for (const key of selectedBadges) {
      rows = rows.filter((g) => g[key] === true)
    }
    if (opponentSearch) {
      const needle = opponentSearch.toLowerCase()
      rows = rows.filter((g) => g.opponent_name.toLowerCase().includes(needle))
    }
    if (analyzedOnly) {
      rows = rows.filter((g) => g.analysis_status === 'done')
    }
    return rows.slice(0, MAX_ROWS)
  }, [games, selectedBadges, opponentSearch, analyzedOnly])

  function toggleBadge(key: keyof BadgeFlags) {
    setSelectedBadges((prev) => (prev.includes(key) ? prev.filter((b) => b !== key) : [...prev, key]))
  }

  if (loading) return <p className="p-8 text-[var(--cw-muted)]">Loading…</p>
  if (error || !games) {
    return (
      <p className="p-8 text-negative">
        Couldn&apos;t load your games. Confirm the Chesswright API server is running.
      </p>
    )
  }

  const totalBadged = games.filter((g) => g.badge_count > 0).length
  const totalAnalyzed = games.filter((g) => g.analysis_status === 'done').length
  const showPlatform = games.some((g) => g.platform === 'Chess.com')

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Game Explorer</h1>

      <p className="mt-2 text-sm text-[var(--cw-muted)]">
        {games.length.toLocaleString()} games total ({totalBadged.toLocaleString()} with at
        least one badge)
      </p>
      {games.length > 0 && (
        <p className="mt-1 text-xs text-[var(--cw-muted)]">
          {totalAnalyzed.toLocaleString()} of {games.length.toLocaleString()} analyzed (
          {((100 * totalAnalyzed) / games.length).toFixed(1)}%) — badges except Giant-killing
          need engine analysis.
        </p>
      )}

      <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <h2 className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
          Filter
        </h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {BADGE_CHIPS.map((chip) => (
            <button
              key={chip.key}
              type="button"
              aria-pressed={selectedBadges.includes(chip.key)}
              onClick={() => toggleBadge(chip.key)}
              className={`rounded-full border px-2.5 py-1 font-condensed text-[10px] ${
                selectedBadges.includes(chip.key)
                  ? 'border-[var(--cw-copper)] text-[var(--cw-copper)]'
                  : 'border-[var(--cw-line)] text-[var(--cw-muted)]'
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>
        <label className="mt-3 block text-xs text-[var(--cw-muted)]">
          Opponent name contains
          <input
            type="text"
            value={opponentSearch}
            onChange={(e) => setOpponentSearch(e.target.value)}
            className="mt-1 block w-full rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-2 py-1 text-[var(--cw-text)]"
          />
        </label>
        <label className="mt-3 flex items-center gap-2 text-xs text-[var(--cw-muted)]">
          <input
            type="checkbox"
            checked={analyzedOnly}
            onChange={(e) => setAnalyzedOnly(e.target.checked)}
          />
          Only show analyzed games
        </label>
      </div>

      <p className="mt-4 text-sm text-[var(--cw-muted)]">
        Showing {filtered.length.toLocaleString()} games, sorted by drama score (most dramatic
        first)
      </p>

      <GameExplorerTable
        games={filtered}
        showPlatform={showPlatform}
        onSelectGame={(gameId) => navigate(`/game-explorer/${gameId}`)}
      />
    </div>
  )
}

import { useMemo, useState } from 'react'
import Slider from './ui/Slider'
import NemesisTable from './NemesisTable'
import OpponentPicker from './OpponentPicker'
import OpponentProfilePanel from './OpponentProfilePanel'
import { useNemesisOpponents } from '../hooks/useNemesisOpponents'

export default function NamedOpponentsTab() {
  const [minGames, setMinGames] = useState(5)
  const { rows, loading, error } = useNemesisOpponents(minGames)
  const [selectedOpponent, setSelectedOpponent] = useState<string | null>(null)

  const toughest = useMemo(() => [...(rows ?? [])].sort((a, b) => a.score_pct - b.score_pct).slice(0, 10), [rows])
  const favorite = useMemo(() => [...(rows ?? [])].sort((a, b) => b.score_pct - a.score_pct).slice(0, 10), [rows])
  const mostPlayed = useMemo(() => [...(rows ?? [])].sort((a, b) => b.n - a.n).slice(0, 10), [rows])
  const surprise = useMemo(() => [...(rows ?? [])].sort((a, b) => a.surprise_pct - b.surprise_pct).slice(0, 10), [rows])
  const opponentNames = useMemo(() => (rows ?? []).map((r) => r.opponent_name), [rows])

  if (loading || error || !rows) return null

  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">
        Ranked by score% (win + 0.5*draw, standard tournament scoring) so repeated draws
        aren&apos;t misread as losses.
      </p>
      <div className="mt-3 w-56">
        <Slider
          id="matchups-nem-min-games"
          label="Minimum games against this opponent"
          min={3}
          max={50}
          value={minGames}
          onChange={setMinGames}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <NemesisTable rows={toughest} title="Toughest opponents (lowest score%)" onSelect={setSelectedOpponent} />
        <NemesisTable rows={favorite} title="Favorite opponents (highest score%)" onSelect={setSelectedOpponent} />
      </div>
      <div className="mt-4">
        <NemesisTable rows={mostPlayed} title="Most-played opponents overall" onSelect={setSelectedOpponent} />
      </div>
      <div className="mt-4">
        <NemesisTable
          rows={surprise}
          title="Biggest surprises (score below Elo expectation)"
          showExpectedSurprise
          onSelect={setSelectedOpponent}
        />
      </div>

      <div className="mt-4">
        <p className="text-xs text-[var(--cw-muted)]">Or find an opponent by name:</p>
        <div className="mt-2">
          <OpponentPicker opponents={opponentNames} onSelect={setSelectedOpponent} />
        </div>
      </div>

      {selectedOpponent && <OpponentProfilePanel opponentName={selectedOpponent} />}
    </div>
  )
}

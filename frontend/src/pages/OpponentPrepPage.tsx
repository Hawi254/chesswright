import { useState } from 'react'
import { Tabs, TabsList, TabsPanel, TabsTab } from '../components/ui/tabs'
import OpponentPrepSearchBox from '../components/OpponentPrepSearchBox'
import RepertoireTab from '../components/RepertoireTab'
import ScoutingNotesTab from '../components/ScoutingNotesTab'
import TournamentPrepTab from '../components/TournamentPrepTab'
import { useOpponentPrepStatus } from '../hooks/useOpponentPrepStatus'
import { useOpponentPrepOpponents, useOpponentPrepReport } from '../hooks/useOpponentPrepReport'
import { API_BASE } from '../lib/apiBase'

const STEP_LABELS: Record<string, string> = {
  migrating: 'Setting up database...',
  fetching: 'Fetching games from lichess...',
  analyzing: 'Running Stockfish analysis...',
  annotating: 'Annotating moves...',
  starting: 'Starting...',
}

export default function OpponentPrepPage() {
  const { data: status } = useOpponentPrepStatus()
  const { opponents } = useOpponentPrepOpponents()
  const [activeUsername, setActiveUsername] = useState<string | null>(null)
  const { report } = useOpponentPrepReport(activeUsername)

  const running = status?.status === 'starting' || status?.status === 'running' || status?.status === 'stopping'
  const errored = status?.status === 'error'

  async function handleScoutNew(username: string, nGames: number) {
    await fetch(`${API_BASE}/api/opponent-prep/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, n_games: nGames }),
    })
    setActiveUsername(username)
  }

  async function handleStop() {
    await fetch(`${API_BASE}/api/opponent-prep/stop`, { method: 'POST' })
  }

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Opponent Prep</h1>

      <div className="mt-4">
        <OpponentPrepSearchBox
          knownOpponents={opponents}
          onLoadKnown={setActiveUsername}
          onScoutNew={handleScoutNew}
        />
      </div>

      {running && status && (
        <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
          <p className="text-xs text-[var(--cw-text)]">
            Analysing <strong>{status.username}</strong>: {STEP_LABELS[status.step ?? ''] ?? status.step}
          </p>
          {status.status !== 'stopping' && (
            <button
              type="button"
              onClick={handleStop}
              className="mt-2 rounded border border-[var(--cw-line)] px-2 py-1 font-condensed text-xs text-[var(--cw-text)]"
            >
              Stop analysis
            </button>
          )}
        </div>
      )}

      {errored && status && (
        <div className="mt-4 rounded-md border border-negative bg-[var(--cw-panel-2)] p-4">
          <p className="text-xs text-negative">Analysis failed: {status.error}</p>
          <p className="mt-1 text-[10px] text-[var(--cw-muted)]">
            Check that the username is spelled correctly and Stockfish is installed.
          </p>
        </div>
      )}

      {!running && !errored && report && (
        <>
          <div className="mt-4 flex gap-6 text-xs text-[var(--cw-text)]">
            <span>{report.gamesAnalyzed} games analysed</span>
            <span>{report.colorSplit.white} White / {report.colorSplit.black} Black</span>
            {report.dateRange.from && (
              <span>{report.dateRange.from} &ndash; {report.dateRange.to}</span>
            )}
          </div>

          {report.gamesAnalyzed > 0 && report.gamesAnalyzed < 5 && (
            <p className="mt-2 text-xs text-[var(--cw-muted)]">
              Not enough data yet -- {report.gamesAnalyzed} analyzed game(s), need at least 5 for
              this view to be meaningful. It&apos;ll fill in as more games are analyzed.
            </p>
          )}

          {report.repertoire.length === 0 ? (
            <p className="mt-4 text-xs text-[var(--cw-muted)]">
              Not enough annotated games to compute a report. Re-run after more games finish
              analysis, or try fetching more games.
            </p>
          ) : (
            <Tabs defaultValue="repertoire" className="mt-4">
              <TabsList>
                <TabsTab value="repertoire">Repertoire</TabsTab>
                <TabsTab value="scouting-notes">Scouting Notes</TabsTab>
                <TabsTab value="tournament-prep">Tournament Prep Report</TabsTab>
              </TabsList>
              <TabsPanel value="repertoire"><RepertoireTab repertoire={report.repertoire} /></TabsPanel>
              <TabsPanel value="scouting-notes">
                {activeUsername && <ScoutingNotesTab username={activeUsername} />}
              </TabsPanel>
              <TabsPanel value="tournament-prep">
                {activeUsername && <TournamentPrepTab username={activeUsername} />}
              </TabsPanel>
            </Tabs>
          )}
        </>
      )}
    </div>
  )
}

import Plot from 'react-plotly.js'
import { usePatternsSessions } from '../hooks/usePatternsSessions'
import { Accordion, AccordionItem } from './ui/accordion'
import { barChart, lineChart } from '../lib/charts'
import { THEME } from '../lib/theme'

const NotEnoughData = () => <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>

export default function SessionsTab() {
  const { data, loading, error } = usePatternsSessions()
  if (loading || error || !data) return null
  if (data.session_rollup.length === 0) return <NotEnoughData />

  const { session_rollup, prior_outcome, session_position, event_type, event_name_breakdown } = data

  const recentSessions = session_rollup.slice(-60)
  const acplRecent = recentSessions.filter((r) => r.acpl !== null)
  const nSessionsTotal = session_rollup.length
  const nSessionsAnalyzed = session_rollup.filter((r) => r.n_analyzed > 0).length
  const acplCoveragePct = nSessionsTotal ? (100 * nSessionsAnalyzed) / nSessionsTotal : 0

  const totalGames = session_rollup.reduce((sum, r) => sum + r.n_games, 0)
  const avgGames = totalGames / nSessionsTotal
  const overallWinPct = session_rollup.reduce((sum, r) => sum + r.win_pct * r.n_games, 0) / totalGames

  return (
    <Accordion defaultOpen={['summary', 'win-rate-trend']}>
      <AccordionItem value="summary" title="Session summary">
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
            <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              Total sessions
            </p>
            <p className="mt-1 text-xl text-[var(--cw-text)]">{nSessionsTotal.toLocaleString()}</p>
          </div>
          <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
            <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              Avg. games per session
            </p>
            <p className="mt-1 text-xl text-[var(--cw-text)]">{avgGames.toFixed(1)}</p>
          </div>
          <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
            <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              Overall win rate
            </p>
            <p className="mt-1 text-xl text-[var(--cw-text)]">{overallWinPct.toFixed(1)}%</p>
          </div>
        </div>
      </AccordionItem>

      <AccordionItem value="win-rate-trend" title="Win rate over time">
        <Plot
          {...lineChart(recentSessions, 'session_start', 'win_pct', THEME.positive, {
            xTitle: 'Session start', yTitle: 'Win rate (%)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
        {session_rollup.length > 60 && (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">
            Showing the most recent 60 of {session_rollup.length} sessions.
          </p>
        )}
      </AccordionItem>

      <AccordionItem value="games-per-session" title="Games per session">
        <Plot
          {...barChart(recentSessions, 'session_start', 'n_games', THEME.accentGold, {
            xTitle: 'Session start', yTitle: 'Games in session',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="acpl-trend" title="ACPL trend across sessions">
        {acplRecent.length === 0 ? (
          <NotEnoughData />
        ) : (
          <Plot
            {...lineChart(acplRecent, 'session_start', 'acpl', THEME.negative, {
              xTitle: 'Session start', yTitle: 'ACPL (lower = more accurate)',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        )}
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          ACPL coverage: {nSessionsAnalyzed} of {nSessionsTotal} sessions ({acplCoveragePct.toFixed(1)}%) have at
          least one analyzed move; the rest show no ACPL line above, not a zero.
        </p>
      </AccordionItem>

      <AccordionItem value="all-sessions" title="All sessions">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              <th scope="col" className="py-2 pr-3">Session start</th>
              <th scope="col" className="py-2 pr-3">Session end</th>
              <th scope="col" className="py-2 pr-3">Games</th>
              <th scope="col" className="py-2 pr-3">Win %</th>
              <th scope="col" className="py-2 pr-3">Draw %</th>
              <th scope="col" className="py-2 pr-3">Loss %</th>
              <th scope="col" className="py-2 pr-3">ACPL</th>
              <th scope="col" className="py-2">Analyzed</th>
            </tr>
          </thead>
          <tbody>
            {session_rollup.map((row) => (
              <tr key={row.session_start} className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
                <td className="py-2 pr-3">{row.session_start}</td>
                <td className="py-2 pr-3">{row.session_end}</td>
                <td className="py-2 pr-3">{row.n_games}</td>
                <td className="py-2 pr-3">{row.win_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{row.draw_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{row.loss_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{row.acpl === null ? '--' : row.acpl.toFixed(1)}</td>
                <td className="py-2">{row.n_analyzed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </AccordionItem>

      <AccordionItem value="prior-outcome" title="Performance after a win vs. after a loss">
        <Plot
          {...barChart(prior_outcome, 'bucket', 'acpl', THEME.negative, {
            xTitle: 'Situation', yTitle: 'ACPL (lower = more accurate)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="session-position" title="Performance by position within a session">
        <Plot
          {...barChart(session_position, 'position', 'acpl', THEME.negative, {
            xTitle: 'Game within the playing session', yTitle: 'ACPL (lower = more accurate)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="event-type" title="Casual vs. tournament & arena play">
        {event_type.length === 0 ? (
          <NotEnoughData />
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {event_type.map((row) => (
              <div key={row.category}>
                <p className="font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]">
                  {row.category}
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
                    <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                      Win rate
                    </p>
                    <p className="mt-1 text-xl text-[var(--cw-text)]">{row.win_pct.toFixed(1)}%</p>
                  </div>
                  <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
                    <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                      ACPL
                    </p>
                    <p className="mt-1 text-xl text-[var(--cw-text)]">
                      {row.acpl === null ? '--' : row.acpl.toFixed(1)}
                    </p>
                  </div>
                </div>
                <p className="mt-1 text-xs text-[var(--cw-muted)]">
                  {row.n_games.toLocaleString()} games, {row.draw_pct.toFixed(1)}% draws
                </p>
              </div>
            ))}
          </div>
        )}
      </AccordionItem>

      <AccordionItem value="event-name-breakdown" title="Named tournaments & arenas">
        {event_name_breakdown.length === 0 ? (
          <NotEnoughData />
        ) : (
          <>
            <p className="mb-2 text-xs text-[var(--cw-muted)]">
              Showing {event_name_breakdown.length} tournament{event_name_breakdown.length === 1 ? '' : 's'}/arena
              {event_name_breakdown.length === 1 ? '' : 's'} with enough games played.
            </p>
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                  <th scope="col" className="py-2 pr-3">Tournament / arena</th>
                  <th scope="col" className="py-2 pr-3">Games</th>
                  <th scope="col" className="py-2 pr-3">Win %</th>
                  <th scope="col" className="py-2 pr-3">Draw %</th>
                  <th scope="col" className="py-2 pr-3">Loss %</th>
                  <th scope="col" className="py-2 pr-3">ACPL</th>
                  <th scope="col" className="py-2">Analyzed</th>
                </tr>
              </thead>
              <tbody>
                {event_name_breakdown.map((row) => (
                  <tr key={row.event} className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
                    <td className="py-2 pr-3">{row.event}</td>
                    <td className="py-2 pr-3">{row.n_games}</td>
                    <td className="py-2 pr-3">{row.win_pct.toFixed(1)}</td>
                    <td className="py-2 pr-3">{row.draw_pct.toFixed(1)}</td>
                    <td className="py-2 pr-3">{row.loss_pct.toFixed(1)}</td>
                    <td className="py-2 pr-3">{row.acpl === null ? '--' : row.acpl.toFixed(1)}</td>
                    <td className="py-2">{row.n_analyzed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </AccordionItem>
    </Accordion>
  )
}

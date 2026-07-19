import Plot from 'react-plotly.js'
import { usePatternsClockTime } from '../hooks/usePatternsClockTime'
import { Accordion, AccordionItem } from './ui/accordion'
import { barChart } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function ClockTimeTab() {
  const { data, loading, error } = usePatternsClockTime()
  if (loading || error || !data) return null

  return (
    <Accordion defaultOpen={['time-pressure']}>
      <AccordionItem value="time-pressure" title="Blunder rate vs. time pressure (clock remaining)">
        <Plot
          {...barChart(data.blunder_rate_by_time_pressure, 'bucket', 'blunder_rate', THEME.negative, {
            xTitle: 'Clock remaining',
            yTitle: 'Blunder rate (% of moves)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="time-control" title="ACPL by time control">
        <Plot
          {...barChart(data.acpl_by_time_control, 'time_control', 'acpl', THEME.negative, {
            xTitle: 'Time control',
            yTitle: 'ACPL (lower = more accurate)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="thinking-time" title="Blunder rate vs. thinking time">
        <p className="mb-2 text-xs text-[var(--cw-muted)]">
          Time spent on this move before playing it. Counter-intuitively, longer thinking time
          doesn&apos;t always mean fewer blunders -- hard positions tend to get more thought AND
          produce more mistakes.
        </p>
        <Plot
          {...barChart(data.thinking_time_blunder_correlation, 'bucket', 'blunder_rate', THEME.negative, {
            xTitle: 'Time spent on the move',
            yTitle: 'Blunder rate (% of moves)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="instant-moves" title="Instant moves (0s recorded thinking time)">
        <p className="mb-2 text-xs text-[var(--cw-muted)]">
          Lichess and chess.com clocks only resolve to the nearest second, so this can&apos;t
          tell a genuinely pre-queued premove apart from an instantly-recognized recapture or
          book move -- there&apos;s no way to know which for sure. What it CAN show: how often
          this happens by game phase, and whether it correlates with worse moves once the
          opening (book-move familiarity, not fast-play behavior) is excluded.
        </p>
        {data.instant_move_rate_by_phase.length === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <Plot
            {...barChart(data.instant_move_rate_by_phase, 'bucket', 'instant_pct', THEME.negative, {
              xTitle: 'Game phase',
              yTitle: 'Instant moves (% of moves)',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        )}

        <p className="mt-4 mb-2 text-xs font-semibold text-[var(--cw-text)]">
          Accuracy of instant moves, opening excluded
        </p>
        {data.instant_move_accuracy.n_total_in_scope === 0 || data.instant_move_accuracy.rows.length === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <p className="mb-2 text-xs text-[var(--cw-muted)]">
              Based on {data.instant_move_accuracy.n_analyzed} analyzed instant move(s) out of{' '}
              {data.instant_move_accuracy.n_total_in_scope} total (
              {((100 * data.instant_move_accuracy.n_analyzed) / data.instant_move_accuracy.n_total_in_scope).toFixed(1)}
              % analyzed) -- a small, backlog-skewed sample right now, not a settled finding.
              Fills in as more games are analyzed.
            </p>
            <Plot
              {...barChart(data.instant_move_accuracy.rows, 'bucket', 'blunder_rate', THEME.negative, {
                xTitle: 'Legal replies available',
                yTitle: 'Blunder rate (% of moves)',
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </>
        )}
      </AccordionItem>
    </Accordion>
  )
}

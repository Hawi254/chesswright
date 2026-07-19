import Plot from 'react-plotly.js'
import { useMatchupsRatingForm } from '../hooks/useMatchupsRatingForm'
import ClickableGameList from './ClickableGameList'
import { barChart, multiLineChart } from '../lib/charts'
import { THEME } from '../lib/theme'

const GK_REASON_LABEL: Record<string, string> = {
  hung_piece: 'Hung a piece',
  faced_mate: 'Faced a forced mate',
  time_pressure: 'Time pressure',
  other: 'Other / gradual decline',
}

export default function RatingFormTab() {
  const { data, loading, error } = useMatchupsRatingForm()
  if (loading || error || !data) return null

  const { giant_killing_counts: gk, collapse_causes, giant_killing_rate_trend, comeback_collapse } = data
  const upsetPct = gk.n_underdog_games ? (100 * gk.n_upsets) / gk.n_underdog_games : null
  const collapsePct = gk.n_favorite_games ? (100 * gk.n_collapses) / gk.n_favorite_games : null

  const explainedReasons = collapse_causes.reason.filter((r) => r.reason !== 'not_analyzed')
  const nTotal = collapse_causes.reason.reduce((sum, r) => sum + r.n, 0)
  const nExplained = explainedReasons.reduce((sum, r) => sum + r.n, 0)
  const reasonChart = explainedReasons.map((r) => ({
    reason: GK_REASON_LABEL[r.reason] ?? r.reason,
    pct: nExplained ? (100 * r.n) / nExplained : 0,
  }))

  const trendChart = multiLineChart(
    giant_killing_rate_trend, 'label',
    [
      { y: 'pct_upset', label: 'upset win rate (300+ underdog)', color: THEME.positive },
      { y: 'pct_collapse', label: 'collapse loss rate (300+ favorite)', color: THEME.negative },
    ],
    { xTitle: 'Quarter', yTitle: '% of games' },
  )

  return (
    <div>
      <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <h2 className="font-condensed text-sm text-[var(--cw-text)]">Win rate vs. rating differential</h2>
        <p className="mt-1 text-xs text-[var(--cw-muted)]">
          Your rating minus the opponent&apos;s: bars left of 0 are games against higher-rated
          opponents, right of 0 against lower-rated ones.
        </p>
        <Plot
          {...barChart(data.win_rate_by_rating_diff, 'band', 'win_pct', THEME.positive, {
            xTitle: 'Rating difference (you minus opponent)', yTitle: 'Win rate (%)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </div>

      <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <h2 className="font-condensed text-sm text-[var(--cw-text)]">Win rate by color, rating-adjusted</h2>
        <p className="mt-1 text-xs text-[var(--cw-muted)]">
          Confirms White&apos;s edge holds at every rating bucket, not just on average.
        </p>
        <table className="mt-2 w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              <th scope="col" className="py-2 pr-3">Rating bucket</th>
              <th scope="col" className="py-2 pr-3">Black (win %)</th>
              <th scope="col" className="py-2">White (win %)</th>
            </tr>
          </thead>
          <tbody>
            {data.color_performance_by_rating.map((row) => (
              <tr key={row.rating_bucket} className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
                <td className="py-2 pr-3 capitalize">{row.rating_bucket}</td>
                <td className="py-2 pr-3">{row.black === null ? '--' : row.black.toFixed(1)}</td>
                <td className="py-2">{row.white === null ? '--' : row.white.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
          <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
            Giant-killing wins (300+ underdog)
          </p>
          <p className="mt-1 text-xl text-[var(--cw-text)]">{gk.n_upsets} / {gk.n_underdog_games}</p>
          {upsetPct !== null && (
            <p className="mt-1 text-xs text-[var(--cw-muted)]">You win {upsetPct.toFixed(1)}% of games as a heavy underdog.</p>
          )}
        </div>
        <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
          <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
            Collapse losses (300+ favorite)
          </p>
          <p className="mt-1 text-xl text-[var(--cw-text)]">{gk.n_collapses} / {gk.n_favorite_games}</p>
          {collapsePct !== null && (
            <p className="mt-1 text-xs text-[var(--cw-muted)]">You lose {collapsePct.toFixed(1)}% of games as a heavy favorite.</p>
          )}
        </div>
      </div>

      <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <h2 className="font-condensed text-sm text-[var(--cw-text)]">Why collapses happen</h2>
        {nTotal === 0 ? (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <p className="mt-1 text-xs text-[var(--cw-muted)]">
              {nExplained} of {nTotal} collapses ({((100 * nExplained) / nTotal).toFixed(0)}%) have some explanation found below.
            </p>
            {nExplained === 0 ? (
              <p className="mt-2 text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
            ) : (
              <>
                <Plot
                  {...barChart(reasonChart, 'reason', 'pct', THEME.accentGold, {
                    xTitle: 'Cause', yTitle: '% of explained collapses',
                  })}
                  config={{ displayModeBar: false }}
                  style={{ width: '100%' }}
                />
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-[var(--cw-text)]">Which piece hung</p>
                    {collapse_causes.piece.length === 0 ? (
                      <p className="mt-1 text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
                    ) : (
                      <Plot
                        {...barChart(collapse_causes.piece, 'piece_name', 'pct', THEME.negative, {
                          xTitle: 'Piece hung', yTitle: '% of hung-piece collapses',
                        })}
                        config={{ displayModeBar: false }}
                        style={{ width: '100%' }}
                      />
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-[var(--cw-text)]">How many moves to mate</p>
                    {collapse_causes.mate.length === 0 ? (
                      <p className="mt-1 text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
                    ) : (
                      <Plot
                        {...barChart(collapse_causes.mate, 'bucket', 'pct', THEME.negative, {
                          xTitle: 'Forced mate distance', yTitle: '% of faced-mate collapses',
                        })}
                        config={{ displayModeBar: false }}
                        style={{ width: '100%' }}
                      />
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>

      <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <h2 className="font-condensed text-sm text-[var(--cw-text)]">Giant-killing rate over time</h2>
        {giant_killing_rate_trend.length < 2 ? (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <Plot {...trendChart} config={{ displayModeBar: false }} style={{ width: '100%' }} />
        )}
      </div>

      <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <h2 className="font-condensed text-sm text-[var(--cw-text)]">Comebacks and collapses (eval-based)</h2>
        <p className="mt-1 text-xs text-[var(--cw-muted)]">
          Comeback: you won or drew a game the engine judged clearly lost for you at some point.
          Collapse: the reverse.
        </p>
        <div className="mt-2 grid grid-cols-2 gap-4">
          <div>
            <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">Comebacks</p>
            <p className="mt-1 text-xl text-[var(--cw-text)]">{comeback_collapse.n_comebacks}</p>
            <ClickableGameList gameIds={comeback_collapse.comeback_game_ids} basePath="matchups" />
          </div>
          <div>
            <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">Collapses</p>
            <p className="mt-1 text-xl text-[var(--cw-text)]">{comeback_collapse.n_collapses}</p>
            <ClickableGameList gameIds={comeback_collapse.collapse_game_ids} basePath="matchups" />
          </div>
        </div>
      </div>
    </div>
  )
}

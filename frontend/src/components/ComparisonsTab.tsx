import Plot from 'react-plotly.js'
import { usePatternsComparisons } from '../hooks/usePatternsComparisons'
import { Accordion, AccordionItem } from './ui/accordion'
import { overlayBarChart } from '../lib/charts'
import { THEME } from '../lib/theme'

// Pure client-side filter, replaces the 4 separate df[df.x == y] call
// sites in _render_tab_comparisons -- generic over row shape so it
// serves rating_bucket/outcome/color/time_bucket splits alike.
function splitBy<T extends Record<string, unknown>>(rows: T[], key: keyof T, value: string): T[] {
  return rows.filter((row) => row[key] === value)
}

// Powers the even-strength weighted-average caption in panel 2.
function weightedAverage<T extends Record<string, unknown>>(
  rows: T[],
  valueCol: keyof T,
  weightCol: keyof T,
): number | null {
  const totalWeight = rows.reduce((sum, row) => sum + (row[weightCol] as number), 0)
  if (totalWeight === 0) return null
  const weightedSum = rows.reduce(
    (sum, row) => sum + (row[valueCol] as number) * (row[weightCol] as number), 0)
  return weightedSum / totalWeight
}

// Intersection of `key` values present in both row sets -- restricts
// panel 6's critical-vs-plenty comparison to opening families with data
// in both clock situations.
function commonFamilies<T extends Record<string, unknown>>(a: T[], b: T[], key: keyof T): Set<string> {
  const bValues = new Set(b.map((row) => String(row[key])))
  return new Set(a.filter((row) => bValues.has(String(row[key]))).map((row) => String(row[key])))
}

// Same shape as PositionsTab.tsx's coverageCaption -- ported from
// patterns_view.py's _coverage_caption, duplicated locally per this
// codebase's established per-component convention (not exported/shared).
function coverageCaption(
  winRows: Array<{ n_games: number; [key: string]: unknown }>,
  acplRows: Array<{ n_games: number; [key: string]: unknown }>,
  keyField: string,
): string | null {
  if (acplRows.length === 0) return null
  const acplByKey = new Map(acplRows.map((r) => [String(r[keyField]), r.n_games]))
  let totalAnalyzed = 0
  let totalGames = 0
  const parts = winRows.map((w) => {
    const key = String(w[keyField])
    const nAnalyzed = acplByKey.get(key) ?? 0
    totalAnalyzed += nAnalyzed
    totalGames += w.n_games
    const pct = w.n_games ? (100 * nAnalyzed) / w.n_games : 0
    return `${key}: ${nAnalyzed} of ${w.n_games} (${pct.toFixed(1)}%)`
  })
  return (
    `ACPL/blunder-rate coverage is thin and backlog-skewed (only ${totalAnalyzed} of ` +
    `${totalGames} games total have any engine analysis) -- win rate above is full-coverage ` +
    'and honest from day one, but treat the accuracy numbers below as suggestive, not settled: ' +
    `${parts.join('; ')}.`
  )
}

const BUCKET_ORDER = ['underdog', 'even', 'favorite'] as const
const BUCKET_LABELS: Record<string, string> = { underdog: 'Underdog', even: 'Even', favorite: 'Favorite' }
const NotEnoughData = () => <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>

export default function ComparisonsTab() {
  const { data, loading, error } = usePatternsComparisons()
  if (loading || error || !data) return null

  const { favorite_underdog, clock_pressure_by_rating_bucket, openings_by_rating_bucket,
    clock_pressure_by_outcome, clock_pressure_by_color, clock_pressure_by_opening } = data

  const underdogCp = splitBy(clock_pressure_by_rating_bucket, 'rating_bucket', 'underdog')
  const favoriteCp = splitBy(clock_pressure_by_rating_bucket, 'rating_bucket', 'favorite')
  const evenCp = splitBy(clock_pressure_by_rating_bucket, 'rating_bucket', 'even')
  const evenWeightedAcpl = weightedAverage(evenCp, 'acpl', 'n_moves')
  const evenWeightedBlunder = weightedAverage(evenCp, 'blunder_rate', 'n_moves')
  const evenTotalMoves = evenCp.reduce((sum, r) => sum + r.n_moves, 0)

  const underdogFavoriteOpenings = openings_by_rating_bucket.filter(
    (r) => r.rating_bucket === 'underdog' || r.rating_bucket === 'favorite')
  const underdogOpenings = splitBy(underdogFavoriteOpenings, 'rating_bucket', 'underdog')
  const favoriteOpenings = splitBy(underdogFavoriteOpenings, 'rating_bucket', 'favorite')

  const winCp = splitBy(clock_pressure_by_outcome, 'outcome', 'win')
  const lossCp = splitBy(clock_pressure_by_outcome, 'outcome', 'loss')

  const whiteCp = splitBy(clock_pressure_by_color, 'color', 'white')
  const blackCp = splitBy(clock_pressure_by_color, 'color', 'black')

  const criticalOAll = splitBy(clock_pressure_by_opening, 'time_bucket', 'critical (<5%)')
  const plentyOAll = splitBy(clock_pressure_by_opening, 'time_bucket', 'plenty (60-100%)')
  const common = commonFamilies(criticalOAll, plentyOAll, 'opening_family')
  const criticalO = criticalOAll.filter((r) => common.has(r.opening_family))
  const plentyO = plentyOAll.filter((r) => common.has(r.opening_family))

  return (
    <Accordion defaultOpen={['favorite-underdog', 'clock-pressure-rating']}>
      <AccordionItem value="favorite-underdog" title="Favorite vs. underdog: overall record">
        {favorite_underdog.win.length === 0 ? (
          <NotEnoughData />
        ) : (
          <>
            <div className="grid grid-cols-3 gap-4">
              {BUCKET_ORDER.map((bucket) => {
                const winRow = favorite_underdog.win.find((r) => r.bucket === bucket)
                if (!winRow) {
                  return (
                    <p key={bucket} className="text-xs text-[var(--cw-muted)]">
                      {BUCKET_LABELS[bucket]}: no games
                    </p>
                  )
                }
                const acplRow = favorite_underdog.acpl.find((r) => r.bucket === bucket)
                return (
                  <div key={bucket} className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
                    <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                      {BUCKET_LABELS[bucket]} win rate
                    </p>
                    <p className="mt-1 text-xl text-[var(--cw-text)]">{winRow.win_pct.toFixed(1)}%</p>
                    <p className="mt-1 text-xs text-[var(--cw-muted)]">{winRow.n_games} games</p>
                    <p className="mt-1 text-xs text-[var(--cw-muted)]">
                      {acplRow ? `ACPL: ${acplRow.acpl.toFixed(1)}` : 'ACPL: no analyzed games yet'}
                    </p>
                  </div>
                )
              })}
            </div>
            {(() => {
              const caption = coverageCaption(favorite_underdog.win, favorite_underdog.acpl, 'bucket')
              return caption ? <p className="mt-2 text-xs text-[var(--cw-muted)]">{caption}</p> : null
            })()}
          </>
        )}
      </AccordionItem>

      <AccordionItem value="clock-pressure-rating" title="Clock pressure: underdog vs. favorite">
        {clock_pressure_by_rating_bucket.length === 0 ? (
          <NotEnoughData />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Plot
                {...overlayBarChart(
                  { rows: underdogCp, x: 'time_bucket', y: 'acpl', label: 'Underdog', color: THEME.accentGold },
                  { rows: favoriteCp, x: 'time_bucket', y: 'acpl', label: 'Favorite', color: THEME.cwCyan },
                  { height: 240, xTitle: 'Clock remaining', yTitle: 'ACPL (lower = more accurate)' },
                )}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
              <Plot
                {...overlayBarChart(
                  { rows: underdogCp, x: 'time_bucket', y: 'blunder_rate', label: 'Underdog', color: THEME.accentGold },
                  { rows: favoriteCp, x: 'time_bucket', y: 'blunder_rate', label: 'Favorite', color: THEME.cwCyan },
                  { height: 240, xTitle: 'Clock remaining', yTitle: 'Blunder rate (% of moves)' },
                )}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
            {evenWeightedAcpl !== null && evenWeightedBlunder !== null && (
              <p className="mt-2 text-xs text-[var(--cw-muted)]">
                Even-strength games: ACPL {evenWeightedAcpl.toFixed(1)}, blunder rate{' '}
                {evenWeightedBlunder.toFixed(1)}% across all clock-pressure levels combined ({evenTotalMoves}{' '}
                analyzed moves).
              </p>
            )}
          </>
        )}
      </AccordionItem>

      <AccordionItem value="openings-rating" title="Openings: underdog vs. favorite win rate">
        {underdogFavoriteOpenings.length === 0 ? (
          <NotEnoughData />
        ) : (
          <Plot
            {...overlayBarChart(
              { rows: underdogOpenings, x: 'opening_family', y: 'win_pct', label: 'Underdog', color: THEME.accentGold },
              { rows: favoriteOpenings, x: 'opening_family', y: 'win_pct', label: 'Favorite', color: THEME.cwCyan },
              { xTitle: 'Opening', yTitle: 'Win rate (%)' },
            )}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        )}
        {openings_by_rating_bucket.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              See all three buckets, including even-strength games
            </summary>
            <table className="mt-2 w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                  <th scope="col" className="py-2 pr-3">Rating bucket</th>
                  <th scope="col" className="py-2 pr-3">Opening</th>
                  <th scope="col" className="py-2 pr-3">Games</th>
                  <th scope="col" className="py-2">Win %</th>
                </tr>
              </thead>
              <tbody>
                {openings_by_rating_bucket.map((row, i) => (
                  <tr key={`${row.rating_bucket}-${row.opening_family}-${i}`}
                    className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
                    <td className="py-2 pr-3">{row.rating_bucket}</td>
                    <td className="py-2 pr-3">{row.opening_family}</td>
                    <td className="py-2 pr-3">{row.n_games}</td>
                    <td className="py-2">{row.win_pct.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </AccordionItem>

      <AccordionItem value="clock-pressure-outcome" title="Clock pressure: wins vs. losses">
        {clock_pressure_by_outcome.length === 0 ? (
          <NotEnoughData />
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <Plot
              {...overlayBarChart(
                { rows: winCp, x: 'time_bucket', y: 'acpl', label: 'Won', color: THEME.positive },
                { rows: lossCp, x: 'time_bucket', y: 'acpl', label: 'Lost', color: THEME.negative },
                { height: 240, xTitle: 'Clock remaining', yTitle: 'ACPL (lower = more accurate)' },
              )}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
            <Plot
              {...overlayBarChart(
                { rows: winCp, x: 'time_bucket', y: 'blunder_rate', label: 'Won', color: THEME.positive },
                { rows: lossCp, x: 'time_bucket', y: 'blunder_rate', label: 'Lost', color: THEME.negative },
                { height: 240, xTitle: 'Clock remaining', yTitle: 'Blunder rate (% of moves)' },
              )}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>
        )}
      </AccordionItem>

      <AccordionItem value="clock-pressure-color" title="Clock pressure: as White vs. as Black">
        {clock_pressure_by_color.length === 0 ? (
          <NotEnoughData />
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <Plot
              {...overlayBarChart(
                { rows: whiteCp, x: 'time_bucket', y: 'acpl', label: 'White', color: THEME.accentGold },
                { rows: blackCp, x: 'time_bucket', y: 'acpl', label: 'Black', color: THEME.cwCyan },
                { height: 240, xTitle: 'Clock remaining', yTitle: 'ACPL (lower = more accurate)' },
              )}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
            <Plot
              {...overlayBarChart(
                { rows: whiteCp, x: 'time_bucket', y: 'blunder_rate', label: 'White', color: THEME.accentGold },
                { rows: blackCp, x: 'time_bucket', y: 'blunder_rate', label: 'Black', color: THEME.cwCyan },
                { height: 240, xTitle: 'Clock remaining', yTitle: 'Blunder rate (% of moves)' },
              )}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>
        )}
      </AccordionItem>

      <AccordionItem value="openings-clock" title="Openings: accuracy under time pressure">
        {clock_pressure_by_opening.length === 0 || criticalO.length === 0 ? (
          <NotEnoughData />
        ) : (
          <Plot
            {...overlayBarChart(
              { rows: criticalO, x: 'opening_family', y: 'acpl', label: 'Critical clock', color: THEME.negative },
              { rows: plentyO, x: 'opening_family', y: 'acpl', label: 'Plenty of clock', color: THEME.positive },
              { xTitle: 'Opening', yTitle: 'ACPL (lower = more accurate)' },
            )}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        )}
      </AccordionItem>
    </Accordion>
  )
}

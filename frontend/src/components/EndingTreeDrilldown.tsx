import Plot from 'react-plotly.js'
import ClickableGameList from './ClickableGameList'
import { barChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { Breadcrumb } from '../lib/endingTree'
import type { EndingDrilldownData } from '../hooks/useEndingTreeDrilldown'

const SECONDARY_CHART_TITLES: Record<string, { xTitle: string; yTitle: string }> = {
  piece: { xTitle: 'Piece hung', yTitle: '% of hung-piece resignation losses' },
  mate: { xTitle: 'Forced mate distance', yTitle: '% of faced-mate resignation losses' },
  scramble: { xTitle: "Opponent's remaining time", yTitle: '% of time-forfeit losses in this bucket' },
}

export default function EndingTreeDrilldown({
  breadcrumb,
  drilldown,
  loading,
}: {
  breadcrumb: Breadcrumb
  drilldown: EndingDrilldownData | null
  loading: boolean
}) {
  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
      <p className="font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-muted)]">
        {breadcrumb.segments.join(' → ')}
      </p>
      <p className="mt-1 text-sm text-[var(--cw-text)]">
        {breadcrumb.count.toLocaleString()} game(s)
        {breadcrumb.pctOfParent !== null && ` — ${breadcrumb.pctOfParent.toFixed(0)}% of its parent`}
      </p>

      {loading && <p className="mt-3 text-xs text-[var(--cw-muted)]">Loading…</p>}

      {!loading && drilldown === null && (
        <p className="mt-3 text-xs text-[var(--cw-muted)]">Click a segment above to see the games behind it.</p>
      )}

      {!loading && drilldown && (
        <>
          <div className="mt-3">
            <ClickableGameList gameIds={drilldown.gameIds} basePath="game-endings" />
            {drilldown.total > drilldown.gameIds.length && (
              <p className="mt-1 text-xs text-[var(--cw-muted)]">
                +{(drilldown.total - drilldown.gameIds.length).toLocaleString()} more
              </p>
            )}
          </div>

          {drilldown.secondaryChart && drilldown.secondaryChartKind && (
            <div className="mt-4">
              <Plot
                {...barChart(drilldown.secondaryChart, 'label', 'pct', THEME.negative, {
                  height: 240,
                  ...SECONDARY_CHART_TITLES[drilldown.secondaryChartKind],
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}

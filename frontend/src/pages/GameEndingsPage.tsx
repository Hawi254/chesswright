import { useState } from 'react'
import ZoneHead from '../components/ZoneHead'
import EndingStatTile from '../components/EndingStatTile'
import WaffleStat from '../components/WaffleStat'
import EndingTreeIcicle from '../components/EndingTreeIcicle'
import EndingTreeDrilldown from '../components/EndingTreeDrilldown'
import EndgameMaterialSection from '../components/EndgameMaterialSection'
import EndingTrendsPanel from '../components/EndingTrendsPanel'
import { Tabs, TabsList, TabsTab } from '../components/ui/tabs'
import { useEndingTree } from '../hooks/useEndingTree'
import { useEndingTreeDrilldown } from '../hooks/useEndingTreeDrilldown'
import { useEndingSummary } from '../hooks/useEndingSummary'
import { buildBreadcrumb } from '../lib/endingTree'

const TIME_CONTROL_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'bullet', label: 'Bullet' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'classical', label: 'Classical' },
]

export default function GameEndingsPage() {
  const [timeControl, setTimeControl] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  const { tree, loading: treeLoading, error: treeError } = useEndingTree(timeControl)
  const { drilldown, loading: drilldownLoading } = useEndingTreeDrilldown(selectedPath, timeControl)
  const { summary, loading: summaryLoading, error: summaryError } = useEndingSummary()

  function handleNodeClick(path: string) {
    if (path === 'root') {
      setSelectedPath(null)
      return
    }
    // Win/Draw/Loss nodes (a single segment) have no drilldown --
    // get_games_for_ending_node only recognizes 2-segment (result/end
    // type) and 3-segment (resignation cause / time-forfeit bucket)
    // paths, and 400s on anything else. Found live: clicking one of
    // these top-level icicle bands fired a request the backend was
    // always going to reject.
    if (path.split('/').length === 1) return
    setSelectedPath(path)
  }

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Game Endings</h1>

      {!summaryLoading && !summaryError && summary && (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <EndingStatTile
            label="Total games"
            value={summary.hero.total_games > 0 ? `${summary.hero.total_games.toLocaleString()} games` : null}
            detail={
              summary.hero.decisive_pct !== null
                ? `${summary.hero.decisive_pct.toFixed(0)}% decisive, ${summary.hero.draw_pct!.toFixed(0)}% draws`
                : undefined
            }
          />
          <EndingStatTile
            label="Resignation losses explained"
            value={
              summary.hero.resignation_explained_pct !== null
                ? `${summary.hero.resignation_explained_pct.toFixed(0)}% explained`
                : null
            }
          >
            {summary.hero.resignation_explained_pct !== null && (
              <WaffleStat percent={summary.hero.resignation_explained_pct} />
            )}
          </EndingStatTile>
          <EndingStatTile
            label="Flagged while ahead"
            value={
              summary.hero.flagged_while_ahead_pct !== null
                ? `${summary.hero.flagged_while_ahead_pct.toFixed(0)}%`
                : null
            }
            detail="of time-forfeit losses came while you were ahead on material"
            tone="negative"
          />
        </div>
      )}

      <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
        <ZoneHead eyebrow="How your games end" title="Ending Tree" />
        <div className="mt-3">
          <Tabs value={timeControl ?? 'all'} onValueChange={(v) => setTimeControl(v === 'all' ? null : (v as string))}>
            <TabsList>
              {TIME_CONTROL_OPTIONS.map((opt) => (
                <TabsTab key={opt.value} value={opt.value}>
                  {opt.label}
                </TabsTab>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {treeLoading && <p className="mt-4 text-[var(--cw-muted)]">Loading…</p>}
        {!treeLoading && (treeError || !tree) && (
          <p className="mt-4 text-negative">
            Couldn&apos;t load your Ending Tree. Confirm the Chesswright API server is running.
          </p>
        )}
        {!treeLoading && tree && (
          <>
            <div className="mt-3">
              <EndingTreeIcicle tree={tree} onNodeClick={handleNodeClick} />
            </div>
            <EndingTreeDrilldown
              breadcrumb={buildBreadcrumb(tree, selectedPath)}
              drilldown={drilldown}
              loading={drilldownLoading}
            />
          </>
        )}
      </div>

      {!summaryLoading && !summaryError && summary && (
        <>
          <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
            <ZoneHead eyebrow="Game phase reached" title="Endgame Material Reached" />
            <EndgameMaterialSection rows={summary.endgame_material} />
          </div>

          <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
            <ZoneHead eyebrow="Over time" title="Trends" />
            <EndingTrendsPanel
              resignationTrend={summary.resignation_trend}
              timeForfeitTrend={summary.time_forfeit_trend}
            />
          </div>
        </>
      )}
    </div>
  )
}

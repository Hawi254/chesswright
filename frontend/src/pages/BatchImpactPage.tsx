import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import EndpointPicker, { applyChartClick } from '../components/EndpointPicker'
import BatchTrendChart from '../components/BatchTrendChart'
import RangeHeadline from '../components/RangeHeadline'
import RangeRecords from '../components/RangeRecords'
import DumbbellSection from '../components/DumbbellSection'
import NewBlundersInRangeTable from '../components/NewBlundersInRangeTable'
import { useBatchImpact } from '../hooks/useBatchImpact'
import { THEME } from '../lib/theme'
import type { DumbbellRow } from '../lib/charts'
import type { BatchImpactPhaseRow, BatchImpactEndgameRow, BatchImpactMotifRow, BatchImpactSummary } from '../hooks/useBatchImpact'

function metricRows<T extends Record<string, unknown>>(
  rows: T[], categoryKey: keyof T, beforeKey: keyof T, afterKey: keyof T,
): DumbbellRow[] {
  return rows
    .filter((r) => r[beforeKey] !== null && r[afterKey] !== null)
    .map((r) => ({ category: String(r[categoryKey]), before: r[beforeKey] as number, after: r[afterKey] as number }))
}

function phaseRows(rows: BatchImpactPhaseRow[], metric: 'acpl' | 'blunderRate'): DumbbellRow[] {
  return metric === 'acpl'
    ? metricRows(rows, 'phase', 'acplBefore', 'acplAfter')
    : metricRows(rows, 'phase', 'blunderRateBefore', 'blunderRateAfter')
}
function endgameRows(rows: BatchImpactEndgameRow[], metric: 'acpl' | 'blunderRate'): DumbbellRow[] {
  return metric === 'acpl'
    ? metricRows(rows, 'endgameType', 'acplBefore', 'acplAfter')
    : metricRows(rows, 'endgameType', 'blunderRateBefore', 'blunderRateAfter')
}
function motifRows(rows: BatchImpactMotifRow[]): DumbbellRow[] {
  return rows.map((r) => ({ category: r.motif, before: r.before, after: r.after }))
}

export default function BatchImpactPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [pendingFirst, setPendingFirst] = useState<number | null>(null)

  const runAParam = searchParams.get('runA')
  const runBParam = searchParams.get('runB')
  const hasExplicitRange = runBParam !== null
  const runA: number | null | undefined = runAParam === null ? undefined : (runAParam === 'start' ? null : Number(runAParam))
  const runB: number | undefined = runBParam === null ? undefined : Number(runBParam)

  // Writing the resolved default range into the URL (below) flips
  // hasExplicitRange from false to true, which would otherwise change the
  // args passed to useBatchImpact and force a wholly redundant second
  // fetch of data we already have -- a real (if brief) network round trip
  // and content flicker on every default-range page load. This ref makes
  // that one URL-bar sync inert to the hook, matching the plan's own
  // stated intent that it "never re-triggers the default-resolution
  // path" -- only a genuine user interaction (handleRangeChange/
  // handleChartClick) clears it, so real range changes still refetch.
  const suppressNextFetchRef = useRef(false)
  const effectiveHasExplicitRange = hasExplicitRange && !suppressNextFetchRef.current

  const { summary, loading, error, blocked } = useBatchImpact(
    effectiveHasExplicitRange ? runA : undefined,
    effectiveHasExplicitRange ? runB : undefined,
  )

  // useBatchImpact nulls `summary` the instant runA===runB (blocked), which
  // would otherwise take the EndpointPicker down with it -- the one place
  // the user could actually fix their selection. Keep the last-seen runs
  // list around across a blocked transition so the picker survives it.
  // Adjusted during render (React's documented derived-state pattern), not
  // via a useEffect -- an effect here would add an extra commit/render
  // round trip that widens the window where the page's own url-sync-then-
  // refetch cycle transiently nulls `summary` on every default-range load.
  const [lastRuns, setLastRuns] = useState<BatchImpactSummary['runs']>([])
  if (summary && summary.runs !== lastRuns) {
    setLastRuns(summary.runs)
  }

  useEffect(() => {
    if (summary && !hasExplicitRange && summary.range.runB !== null) {
      suppressNextFetchRef.current = true
      setSearchParams(
        { runA: summary.range.runA === null ? 'start' : String(summary.range.runA), runB: String(summary.range.runB) },
        { replace: true },
      )
    }
  }, [summary, hasExplicitRange, setSearchParams])

  function handleRangeChange(newRunA: number | null, newRunB: number) {
    suppressNextFetchRef.current = false
    setPendingFirst(null)
    setSearchParams({ runA: newRunA === null ? 'start' : String(newRunA), runB: String(newRunB) })
  }

  function handleChartClick(clickedRunId: number) {
    suppressNextFetchRef.current = false
    const currentRunB = summary?.range.runB ?? clickedRunId
    const next = applyChartClick(pendingFirst, clickedRunId, currentRunB)
    setPendingFirst(next.pendingFirst)
    setSearchParams({ runA: next.runA === null ? 'start' : String(next.runA), runB: String(next.runB) })
  }

  // Blocked has no summary of its own (useBatchImpact skips the fetch
  // entirely), so range/runs fall back to the last successfully loaded
  // summary -- otherwise the picker would blank out along with the rest
  // of the page the moment runA===runB, taking away the only way to fix it.
  const range = summary
    ? { runA: summary.range.runA, runB: summary.range.runB }
    : blocked
      ? { runA: runA ?? null, runB: runB ?? null }
      : { runA: null, runB: null }
  const counter = summary?.counter ?? null

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Batch Impact</h1>
      <p className="mt-2 max-w-2xl text-sm text-[var(--cw-muted)]">
        Pick any two analysis batches to see exactly what changed between them — accuracy, blunders, and tactical
        motifs, checkpoint to checkpoint.
      </p>

      {loading && lastRuns.length === 0 && <p className="mt-4 text-[var(--cw-muted)]">Loading…</p>}
      {!loading && !blocked && (error || !summary) && lastRuns.length === 0 && (
        <p className="mt-4 text-negative">
          Couldn&apos;t load batch impact data. Confirm the Chesswright API server is running.
        </p>
      )}

      {!loading && !blocked && summary && summary.runs.length === 0 && (
        <p className="mt-4 text-[var(--cw-muted)]">
          No analysis batches yet — start one from Analysis Jobs to see its impact here.
        </p>
      )}

      {lastRuns.length > 0 && (
        <>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
            <EndpointPicker runs={lastRuns} range={range} onChange={handleRangeChange} />
            {counter && (
              <p className="text-xs text-[var(--cw-muted)]">
                {counter.totalBatches} batches, {counter.totalGamesAnalyzed} games analyzed total
              </p>
            )}
          </div>

          {blocked ? null : summary ? (
            <>
              <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
                <BatchTrendChart
                  rows={summary.trend} yKey="cumulativeAcpl" yTitle="ACPL"
                  color={THEME.categoricalSeries[0]} range={range} onPointClick={handleChartClick}
                />
                <BatchTrendChart
                  rows={summary.trend} yKey="cumulativeBlunderRate" yTitle="Blunder rate (%)"
                  color={THEME.categoricalSeries[1]} range={range} onPointClick={handleChartClick}
                />
              </div>

              <RangeHeadline
                headline={summary.headline}
                pendingAnnotation={summary.pendingAnnotation}
                runALabel={summary.range.runA === null ? 'Start' : `Run #${summary.range.runA}`}
                runBLabel={`Run #${summary.range.runB}`}
              />
              <RangeRecords records={summary.records} />

              <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
                <h2 className="font-condensed text-[15px] font-bold text-[var(--cw-text)]">Accuracy by game phase</h2>
                <div className="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <DumbbellSection title="ACPL" rows={phaseRows(summary.phase, 'acpl')} xTitle="ACPL" />
                  <DumbbellSection title="Blunder rate" rows={phaseRows(summary.phase, 'blunderRate')} xTitle="Blunder rate" valueSuffix="%" />
                </div>
              </div>

              <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
                <h2 className="font-condensed text-[15px] font-bold text-[var(--cw-text)]">Endgame accuracy</h2>
                <div className="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <DumbbellSection title="ACPL" rows={endgameRows(summary.endgame, 'acpl')} xTitle="ACPL" />
                  <DumbbellSection title="Blunder rate" rows={endgameRows(summary.endgame, 'blunderRate')} xTitle="Blunder rate" valueSuffix="%" />
                </div>
              </div>

              <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
                <h2 className="font-condensed text-[15px] font-bold text-[var(--cw-text)]">Tactical motifs missed</h2>
                <DumbbellSection title="Missed count" rows={motifRows(summary.motifs)} xTitle="Missed count" />
              </div>

              <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
                <NewBlundersInRangeTable
                  blunders={summary.newBlunders}
                  onSelectGame={(gameId) => navigate(`/batch-impact/${gameId}`)}
                />
              </div>
            </>
          ) : null}
        </>
      )}
    </div>
  )
}

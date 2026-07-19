import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EndingStatTile from '../components/EndingStatTile'
import PointsSankey from '../components/PointsSankey'
import PointsHeadline from '../components/PointsHeadline'
import PointsMonthlyTrend from '../components/PointsMonthlyTrend'
import PointsConversionBreakdown from '../components/PointsConversionBreakdown'
import PointsConversionCauses from '../components/PointsConversionCauses'
import PointsCostliestTable from '../components/PointsCostliestTable'
import { Accordion, AccordionItem } from '../components/ui/accordion'
import { Tabs, TabsList, TabsTab } from '../components/ui/tabs'
import { usePointsLedger } from '../hooks/usePointsLedger'
import { computeHeadline } from '../lib/pointsHeadline'
import type { PointsBucketKey } from '../lib/pointsLabels'

const TIME_CONTROL_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'bullet', label: 'Bullet' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'classical', label: 'Classical' },
]

function thinDataMessage(nAnalyzed: number, minRequired: number): string {
  return `Not enough data yet — ${nAnalyzed} analyzed game(s), need at least ${minRequired} for this ` +
    `view to be meaningful. It'll fill in as more games are analyzed.`
}

export default function PointsPage() {
  const navigate = useNavigate()
  const [timeControl, setTimeControl] = useState<string | null>(null)
  const [activeBucket, setActiveBucket] = useState<PointsBucketKey | null>(null)
  const { summary, loading, error } = usePointsLedger(timeControl)

  useEffect(() => {
    if (!summary || !activeBucket) return
    if (!summary.buckets.some((b) => b.bucket === activeBucket)) setActiveBucket(null)
  }, [summary, activeBucket])

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Where Your Points Go</h1>
      <p className="mt-2 max-w-2xl text-sm text-[var(--cw-muted)]">
        Every analyzed game stores a move-by-move win-probability curve. Read game-shaped, it becomes a
        ledger: what your positions promised at their best, what you actually scored, and which kind of
        collapse ate the difference.
      </p>

      <div className="mt-4">
        <Tabs value={timeControl ?? 'all'} onValueChange={(v) => setTimeControl(v === 'all' ? null : (v as string))}>
          <TabsList>
            {TIME_CONTROL_OPTIONS.map((opt) => (
              <TabsTab key={opt.value} value={opt.value}>{opt.label}</TabsTab>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {loading && <p className="mt-4 text-[var(--cw-muted)]">Loading…</p>}
      {!loading && (error || !summary) && (
        <p className="mt-4 text-negative">
          Couldn&apos;t load your points ledger. Confirm the Chesswright API server is running.
        </p>
      )}

      {!loading && summary && summary.tc_options.length === 0 && (
        <p className="mt-4 text-[var(--cw-muted)]">{thinDataMessage(summary.analyzed_games ?? 0, 1)}</p>
      )}

      {!loading && summary && summary.tc_options.length > 0 && summary.n_games === 0 && (
        <p className="mt-4 text-[var(--cw-muted)]">No analyzed games in this time control yet.</p>
      )}

      {!loading && summary && summary.n_games > 0 && (
        <>
          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
            {summary.buckets.length > 0 && (
              <PointsSankey
                buckets={summary.buckets}
                actualPoints={(summary.actual_pct / 100) * summary.n_games}
                leakedPoints={summary.leaked_points}
                onBucketClick={setActiveBucket}
              />
            )}
            <div className="grid grid-cols-2 gap-3">
              <EndingStatTile label="Games in ledger" value={summary.n_games.toLocaleString()} />
              <EndingStatTile label="Actual score" value={`${summary.actual_pct.toFixed(1)}%`} />
              <EndingStatTile label="Points leaked" value={summary.leaked_points.toFixed(1)} tone="negative" />
              <EndingStatTile label="Ceiling score" value={`${summary.ceiling_pct.toFixed(1)}%`} />
            </div>
          </div>

          {summary.buckets.length === 0 ? (
            <p className="mt-4 text-[var(--cw-muted)]">
              No leaked points found in this slice — every winning position was converted and no even
              game drifted away.
            </p>
          ) : (
            <>
              <div className="mt-4">
                <PointsHeadline
                  headline={computeHeadline(summary.buckets, summary.conversion_breakdown.adv_band, summary.conversion_breakdown.conv_phase)}
                />
              </div>

              {/* Mirrors points_view.py's early `return` right after the
                  no-leaks success message above -- when there are no leaks
                  in this slice, none of the detail sections below have
                  anything to show either, so none of them render. */}
              <PointsMonthlyTrend rows={summary.monthly} />
              <PointsConversionBreakdown
                advBand={summary.conversion_breakdown.adv_band}
                convPhase={summary.conversion_breakdown.conv_phase}
                convClock={summary.conversion_breakdown.conv_clock}
              />
              <PointsConversionCauses
                reason={summary.causes.reason}
                piece={summary.causes.piece}
                mate={summary.causes.mate}
              />

              <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
                <h2 className="font-condensed text-[15px] font-bold text-[var(--cw-text)]">Costliest games</h2>
                <p className="mt-1 text-xs text-[var(--cw-muted)]">
                  The individual games that leaked the most points. Click a row to open that game&apos;s full story.
                </p>
                <PointsCostliestTable
                  games={summary.costliest_games}
                  activeBucket={activeBucket}
                  onClearBucket={() => setActiveBucket(null)}
                  onSelectGame={(gameId) => navigate(`/points/${gameId}`)}
                />
              </div>

              <div className="mt-8">
                <Accordion>
                  <AccordionItem value="methodology" title="How the ledger is scored">
                    <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--cw-muted)]">
                      <li>Only fully analyzed games count, so every curve is complete.</li>
                      <li><strong>Failed conversion</strong>: your win probability reached 70%+ and the game wasn&apos;t won. Leak = peak probability minus points scored.</li>
                      <li><strong>Missed swindle</strong>: you were down to 25% or worse, the opponent let you back to 50%+, and you still lost. Leak = the chance you were given.</li>
                      <li><strong>Failed hold</strong>: at move 15+ you still had 45%+ but never reached winning, and lost. Leak = the half point an even game is worth.</li>
                      <li>Each game lands in at most one bucket (conversion first, then swindle, then hold), so leaked points add up instead of double-counting.</li>
                    </ul>
                  </AccordionItem>
                </Accordion>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

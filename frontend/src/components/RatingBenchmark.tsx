import TrendArrow from './TrendArrow'
import type { HeadlineTrend } from '../hooks/useInsightsData'
import type { HeadlineStats, RatingSnapshot } from '../hooks/useOverviewData'

export default function RatingBenchmark({
  stats,
  ratingSnapshot,
  trend,
}: {
  stats: HeadlineStats
  ratingSnapshot: RatingSnapshot
  trend: HeadlineTrend | null
}) {
  if (stats.implied_rating === null) {
    return (
      <div data-testid="rating-benchmark" className="mt-4">
        <p className="text-xs text-[var(--cw-muted)]">
          Not enough analyzed moves yet for a rating benchmark — check back after more games are
          analyzed.
        </p>
      </div>
    )
  }

  const acplDisplay = stats.acpl !== null ? stats.acpl.toFixed(1) : '--'
  const currentRatingDisplay = ratingSnapshot.current_rating ?? '--'

  return (
    <div
      data-testid="rating-benchmark"
      className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-3"
    >
      <div className="flex items-baseline gap-6">
        <div>
          <div className="text-xs text-[var(--cw-muted)]">Your rating</div>
          <div className="font-mono text-lg font-semibold tabular-nums text-[var(--cw-text)]">
            {currentRatingDisplay}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--cw-muted)]">Implied by your accuracy</div>
          <div className="flex items-baseline font-mono text-lg font-semibold tabular-nums text-[var(--cw-text)]">
            {stats.implied_rating}
            <TrendArrow delta={trend?.implied_rating_delta ?? null} goodDirection="up" />
          </div>
        </div>
      </div>
      <p className="mt-2 text-xs text-[var(--cw-muted)]">
        Players with your overall accuracy ({acplDisplay} ACPL) typically sit around{' '}
        {stats.implied_rating} — a general correlation across many players, not a personal or
        per-finding prediction.
      </p>
      <p className="mt-1 text-[10px] text-[var(--cw-muted)]">
        Source: population-level ACPL-to-rating relationship (Chess Digits&apos; analysis of human
        play, corroborated by Regan &amp; Haworth, &quot;Intrinsic Chess Ratings&quot;).
      </p>
    </div>
  )
}

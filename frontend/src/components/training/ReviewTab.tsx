import { useState } from 'react'
import { useProStatus } from '../../hooks/useProStatus'
import { useReviewStats } from '../../hooks/useReviewStats'
import EndingStatTile from '../EndingStatTile'
import DrillSession from './DrillSession'

function ReviewUpsell() {
  return (
    <div className="p-4">
      <p className="max-w-[60ch] text-xs text-[var(--cw-text)]">
        <strong>Review</strong> is a Chesswright Pro feature. Practice your mistake positions on
        an adaptive spaced-repetition schedule — the positions you keep blundering come back
        sooner, and the ones you've mastered fade into the background. Upgrade to Pro to unlock
        in-app drilling. &rarr;{' '}
        <a href="https://chesswright.gumroad.com" target="_blank" rel="noreferrer" className="text-[var(--cw-copper)]">
          chesswright.gumroad.com
        </a>
      </p>
    </div>
  )
}

export default function ReviewTab() {
  const proStatus = useProStatus()
  const [refreshKey, setRefreshKey] = useState(0)
  const stats = useReviewStats(proStatus.active, refreshKey)

  if (proStatus.loading) return null
  if (!proStatus.active) return <ReviewUpsell />

  // Overall recall: reviews-weighted mean of recall_by_source's per-source
  // rates (same "Good or Easy" definition as srs.py's weekly_recall/
  // recall_by_source). null (not 0) when there's no review history yet,
  // so EndingStatTile shows "Not enough games yet." instead of a
  // misleading 0%.
  const totalReviews = stats?.recall_by_source.reduce((sum, s) => sum + s.n_reviews, 0) ?? 0
  const overallRecall =
    stats && totalReviews > 0
      ? Math.round(
          stats.recall_by_source.reduce((sum, s) => sum + s.recall_pct * s.n_reviews, 0) / totalReviews,
        )
      : null
  const latestWeek = stats && stats.weekly_recall.length > 0 ? stats.weekly_recall[stats.weekly_recall.length - 1] : null

  return (
    <div>
      <div className="grid grid-cols-4 gap-3">
        <EndingStatTile label="Due today" value={stats ? String(stats.counts.due) : null} />
        <EndingStatTile label="New" value={stats ? String(stats.counts.new) : null} />
        <EndingStatTile label="Total cards" value={stats ? String(stats.counts.total) : null} />
        <EndingStatTile
          label="Recall rate"
          value={overallRecall === null ? null : `${overallRecall}%`}
          detail={latestWeek ? `${Math.round(latestWeek.recall_pct)}% this week` : undefined}
        />
      </div>
      <div className="mt-6">
        <DrillSession dueCount={stats?.counts.due ?? 0} onSessionChange={() => setRefreshKey((k) => k + 1)} />
      </div>
    </div>
  )
}

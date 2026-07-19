import EndingStatTile from './EndingStatTile'
import type { BatchImpactHeadline } from '../hooks/useBatchImpact'

export interface RangeHeadlineProps {
  headline: BatchImpactHeadline | null
  pendingAnnotation: boolean
  runALabel: string
  runBLabel: string
}

function arrow(before: number | null, after: number, decimals = 1, suffix = ''): string {
  const beforeText = before === null ? '—' : before.toFixed(decimals) + suffix
  return `${beforeText} → ${after.toFixed(decimals)}${suffix}`
}

export default function RangeHeadline({ headline, pendingAnnotation, runALabel, runBLabel }: RangeHeadlineProps) {
  return (
    <div className="mt-4">
      <p className="text-xs text-[var(--cw-muted)]">Between {runALabel} and {runBLabel}</p>
      {pendingAnnotation ? (
        <p className="mt-2 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-3 text-sm text-[var(--cw-muted)]">
          {runBLabel} hasn&apos;t been through the annotation pass yet — headline numbers will appear once it has.
        </p>
      ) : headline ? (
        <div className="mt-2 grid grid-cols-2 gap-3 md:grid-cols-4">
          <EndingStatTile label="ACPL" value={arrow(headline.acplBefore, headline.acplAfter)} />
          <EndingStatTile label="Blunder rate" value={arrow(headline.blunderRateBefore, headline.blunderRateAfter, 1, '%')} />
          <EndingStatTile label="New blunders / brilliancies" value={`${headline.newBlunders} / ${headline.newBrilliant}`} />
          <EndingStatTile label="Top motif" value={headline.topMotif ? `${headline.topMotif} (${headline.topMotifCount})` : '—'} />
        </div>
      ) : null}
    </div>
  )
}

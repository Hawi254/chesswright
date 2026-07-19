export type ConfidenceTier = 'low' | 'medium' | 'high'

// 3-level width by tier -- no continuous confidence score to interpolate.
const CONFIDENCE_WIDTH: Record<ConfidenceTier, number> = { low: 33, medium: 66, high: 100 }
const CONFIDENCE_LABEL: Record<ConfidenceTier, string> = { low: 'Low', medium: 'Medium', high: 'High' }

export interface ConfidenceBadgeProps {
  tier: ConfidenceTier
  sampleSize?: number
}

export default function ConfidenceBadge({ tier, sampleSize }: ConfidenceBadgeProps) {
  return (
    <div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-[var(--cw-line)]">
        <div className="h-full bg-[var(--cw-cyan)]" style={{ width: `${CONFIDENCE_WIDTH[tier]}%` }} />
      </div>
      <div className="mt-0.5 text-[10px] text-[var(--cw-muted)]">
        {CONFIDENCE_LABEL[tier]} confidence{sampleSize !== undefined ? ` — ${sampleSize} games` : ''}
      </div>
    </div>
  )
}

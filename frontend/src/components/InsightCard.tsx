import type { RelatedFindingPair } from '../lib/relatedFindings'
import type { Finding } from '../hooks/useOverviewData'
import ConfidenceBadge from './ConfidenceBadge'

const SEVERITY_CHIP: Record<Finding['severity'], { label: string; className: string }> = {
  high: { label: 'Critical', className: 'text-negative border-negative/40' },
  medium: { label: 'Moderate', className: 'text-[var(--cw-copper)] border-[var(--cw-copper)]/40' },
  low: { label: 'Minor', className: 'text-[var(--cw-cyan)] border-[var(--cw-cyan)]/40' },
}

// Decision 1: relabeled, not remapped -- same 6 real categories, clearer names.
const CATEGORY_LABEL: Record<Finding['category'], string> = {
  tactical: 'Tactical',
  time: 'Time Management',
  defense: 'King Safety',
  matchup: 'Matchups & Opponents',
  giant_killer: 'Giant-Killing & Collapses',
  general: 'General',
}

export interface InsightCardProps {
  finding: Finding
  variant?: 'default' | 'hero'
  relatedTo?: RelatedFindingPair | null
}

export default function InsightCard({ finding, variant = 'default', relatedTo = null }: InsightCardProps) {
  const severityChip = SEVERITY_CHIP[finding.severity]
  const hasConfidenceBar =
    finding.confidence !== undefined &&
    finding.confidence !== 'insufficient' &&
    finding.sample_size !== undefined

  const isHero = variant === 'hero'
  const relatedOtherTitle = relatedTo?.titles.find((t) => t !== finding.title)

  return (
    <div
      data-testid="insight-card"
      className={
        isHero
          ? 'relative rounded-md p-6'
          : 'rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4'
      }
      style={
        isHero
          ? { background: 'radial-gradient(ellipse 60% 100% at 0% 30%, rgba(224,138,60,0.08), transparent 70%)' }
          : undefined
      }
    >
      <div className="flex items-center justify-between gap-2">
        <h3
          className={
            isHero
              ? 'font-condensed text-lg font-semibold text-[var(--cw-text)]'
              : 'font-condensed text-sm font-semibold text-[var(--cw-text)]'
          }
        >
          {finding.title}
        </h3>
        <span
          className={`shrink-0 rounded border px-2 py-0.5 font-condensed text-[10px] uppercase tracking-[0.08em] ${severityChip.className}`}
        >
          {severityChip.label}
        </span>
      </div>

      <p className={isHero ? 'mt-2 text-xl font-semibold text-[var(--cw-text)]' : 'mt-1 text-sm text-[var(--cw-text)]'}>
        {finding.headline}
      </p>
      <p className="mt-1 max-w-[60ch] text-xs text-[var(--cw-muted)]">{finding.detail}</p>

      <span className="mt-2 inline-block rounded border border-[var(--cw-line)] px-2 py-0.5 font-condensed text-[10px] text-[var(--cw-muted)]">
        {CATEGORY_LABEL[finding.category]}
      </span>

      {hasConfidenceBar && finding.confidence && finding.confidence !== 'insufficient' && (
        <div className="mt-2">
          <ConfidenceBadge tier={finding.confidence} sampleSize={finding.sample_size} />
        </div>
      )}

      {relatedTo && relatedOtherTitle && (
        <p className="mt-2 text-[10px] text-[var(--cw-muted)]">
          Related: {relatedOtherTitle} — {relatedTo.rationale}{' '}
          <span className="italic">({relatedTo.source})</span>
        </p>
      )}
    </div>
  )
}

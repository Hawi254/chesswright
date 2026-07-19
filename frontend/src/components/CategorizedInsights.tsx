import InsightCard from './InsightCard'
import { relatedFindingFor } from '../lib/relatedFindings'
import type { Finding } from '../hooks/useOverviewData'

// Fixed order (not alphabetical) -- roughly severity-of-domain order,
// matching the proposal's suggested browse order.
const CATEGORY_ORDER: Finding['category'][] = [
  'tactical', 'time', 'defense', 'matchup', 'giant_killer', 'general',
]

const CATEGORY_LABEL: Record<Finding['category'], string> = {
  tactical: 'Tactical',
  time: 'Time Management',
  defense: 'King Safety',
  matchup: 'Matchups & Opponents',
  giant_killer: 'Giant-Killing & Collapses',
  general: 'General',
}

export default function CategorizedInsights({ findings }: { findings: Finding[] }) {
  const presentTitles = new Set(findings.map((f) => f.title))

  const groups = CATEGORY_ORDER
    .map((category) => ({ category, items: findings.filter((f) => f.category === category) }))
    .filter((group) => group.items.length > 0)

  if (groups.length === 0) {
    return (
      <p className="mt-4 text-xs text-[var(--cw-muted)]">
        Nothing categorized yet — check back after more games are analyzed.
      </p>
    )
  }

  return (
    <div className="mt-4 flex flex-col gap-6">
      {groups.map(({ category, items }) => (
        <div key={category}>
          <h3 className="font-condensed text-xs font-bold uppercase tracking-[0.1em] text-[var(--cw-muted)]">
            {CATEGORY_LABEL[category]}
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-3">
            {items.map((f) => (
              <InsightCard key={f.title} finding={f} relatedTo={relatedFindingFor(f.title, presentTitles)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

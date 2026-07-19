import InsightCard from './InsightCard'
import ZoneHead from './ZoneHead'
import type { Finding } from '../hooks/useOverviewData'

// Decision 6: neutral round-ups/distributions, plus the surprise-gap
// findings. The finding JSON never exposes raw expected_score_pct/
// score_pct (backend-only intermediates insights.py uses to compute
// severity) -- category === 'matchup' && severity === 'high' is the only
// field-level proxy for "unusually large surprise gap" actually present
// in the payload, and only _nemesis/_best_matchup carry category
// 'matchup', so this can't pull in an unrelated finding.
function isDiscovery(finding: Finding): boolean {
  return finding.polarity === 'neutral' || (finding.category === 'matchup' && finding.severity === 'high')
}

export default function InterestingDiscoveries({ findings }: { findings: Finding[] }) {
  const discoveries = findings.filter(isDiscovery)
  if (discoveries.length === 0) return null

  return (
    <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="Curated" title="Did you know?" />
      <div className="mt-4 grid grid-cols-2 gap-4">
        {discoveries.map((f) => (
          <InsightCard key={f.title} finding={f} />
        ))}
      </div>
    </div>
  )
}

import CategorizedInsights from '../components/CategorizedInsights'
import HeroInsight from '../components/HeroInsight'
import InsightCard from '../components/InsightCard'
import InterestingDiscoveries from '../components/InterestingDiscoveries'
import NarrativePanel from '../components/NarrativePanel'
import PerformanceSummary from '../components/PerformanceSummary'
import RatingBenchmark from '../components/RatingBenchmark'
import RecentImprovements from '../components/RecentImprovements'
import StrengthsWeaknesses from '../components/StrengthsWeaknesses'
import TrainingQueueTeaser from '../components/TrainingQueueTeaser'
import ZoneHead from '../components/ZoneHead'
import { useInsightsCoaching, useInsightsSynthesis } from '../hooks/useInsightsNarratives'
import { useInsightsData } from '../hooks/useInsightsData'
import { relatedFindingFor } from '../lib/relatedFindings'
import { useMilestones } from '../hooks/useMilestones'
import type { Finding } from '../hooks/useOverviewData'

const SEVERITY_RANK: Record<Finding['severity'], number> = { high: 3, medium: 2, low: 1 }

export default function InsightsPage() {
  const { stats, findings, ratingSnapshot, trend, loading, error } = useInsightsData()
  const { milestones } = useMilestones()

  if (loading) {
    return (
      <div className="min-h-full p-8">
        <p className="text-[var(--cw-muted)]">Loading…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-full p-8">
        <p className="text-negative">
          Couldn&apos;t load your Insights data. Confirm the Chesswright API server is running.
        </p>
      </div>
    )
  }

  if (!stats || !findings || !ratingSnapshot || !trend) return <></>

  if (findings.length === 0) {
    return (
      <div className="min-h-full p-8">
        <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Insights</h1>
        <p className="mt-4 text-[var(--cw-muted)]">
          Nothing to show yet — analyze a few more games and check back here.
        </p>
      </div>
    )
  }

  const sorted = [...findings].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity])
  const hero = sorted[0]
  const critical = findings.filter((f) => f.severity === 'high')
  const presentTitles = new Set(findings.map((f) => f.title))

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Insights</h1>
      <p className="mt-1 text-sm text-[var(--cw-muted)]">
        A live digest of what stands out in your analyzed games so far — no curated write-up, just
        whatever the numbers currently show.
      </p>

      <div className="mt-6">
        <HeroInsight finding={hero} />
      </div>

      <PerformanceSummary stats={stats} findings={findings} trend={trend} />

      <RatingBenchmark stats={stats} ratingSnapshot={ratingSnapshot} trend={trend} />

      {critical.length > 0 && (
        <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
          <ZoneHead eyebrow="Highest impact" title="Critical findings" />
          <div className="mt-4 grid grid-cols-2 gap-4">
            {critical.map((f) => (
              <InsightCard key={f.title} finding={f} relatedTo={relatedFindingFor(f.title, presentTitles)} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
        <ZoneHead eyebrow="Where you stand" title="Strengths & weaknesses" />
        <StrengthsWeaknesses findings={findings} />
      </div>

      <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
        <ZoneHead eyebrow="Browse by category" title="Categorized insights" />
        <CategorizedInsights findings={findings} />
      </div>

      <InterestingDiscoveries findings={findings} />

      <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
        <ZoneHead eyebrow="Synthesis" title="What your findings add up to" />
        <NarrativePanel
          useNarrative={useInsightsSynthesis}
          description="Asks Claude to read the findings above and call out what they add up to, rather than just listing them again."
          generateLabel="Generate synthesis"
          regenerateLabel="Regenerate synthesis"
        />
      </div>

      <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
        <ZoneHead eyebrow="Coaching" title="What to practice" />
        <NarrativePanel
          useNarrative={useInsightsCoaching}
          description="Concrete, specific practice recommendations grounded in the findings above — not just what's wrong, but what to actually do about it."
          generateLabel="Generate coaching recommendations"
          regenerateLabel="Regenerate recommendations"
        />
      </div>

      <TrainingQueueTeaser findings={findings} />

      {milestones && <RecentImprovements milestones={milestones} />}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE } from '../../lib/apiBase'
import type { Finding } from '../../hooks/useOverviewData'
import WeaknessCard from './WeaknessCard'
import { DRILL_PRESETS } from '../../lib/trainingPresets'

const SEVERITY_RANK: Record<Finding['severity'], number> = { high: 3, medium: 2, low: 1 }
const MOTIF_GATED_TITLES = new Set(
  Object.entries(DRILL_PRESETS).filter(([, p]) => p.includeMotifs).map(([title]) => title),
)

export default function WeaknessesTab() {
  const [findings, setFindings] = useState<Finding[] | null>(null)
  const [motifBackfillNeeded, setMotifBackfillNeeded] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/overview/career-findings`)
      .then((r) => r.json())
      .then((body: Finding[]) => { if (!cancelled) setFindings(body) })
      .catch(() => { if (!cancelled) setFindings([]) })
    fetch(`${API_BASE}/api/training/motif-backfill-needed`)
      .then((r) => r.json())
      .then((body: { needed: boolean }) => { if (!cancelled) setMotifBackfillNeeded(body.needed) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  if (findings === null) return null

  const weaknesses = findings
    .filter((f) => f.polarity === 'weakness')
    .sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity])

  if (weaknesses.length === 0) {
    return (
      <p className="text-sm text-[var(--cw-muted)]">
        Nothing tagged as a clear weakness yet with the data analyzed so far — check back as more
        games are analyzed, or see the full findings list on Insights.
      </p>
    )
  }

  const gatedQueued = weaknesses.filter((f) => MOTIF_GATED_TITLES.has(f.title))

  return (
    <div>
      {gatedQueued.length > 0 && motifBackfillNeeded && (
        <div className="mb-4 rounded-md border border-[var(--cw-copper)]/40 bg-[var(--cw-panel)] p-3 text-xs text-[var(--cw-text)]">
          {gatedQueued.length} queued {gatedQueued.length === 1 ? 'weakness' : 'weaknesses'} below (
          {gatedQueued.map((f) => f.title).join(', ')}) build practice positions from tactical
          motif data, which hasn't been computed for your analyzed games yet — the practice set
          will be empty until then.{' '}
          <Link to="/analysis-jobs" className="text-[var(--cw-copper)] underline">
            Run annotation pass now →
          </Link>
        </div>
      )}
      <div className="flex flex-col gap-3">
        {weaknesses.map((f) => (
          <WeaknessCard key={f.title} finding={f} />
        ))}
      </div>
    </div>
  )
}

import { Link } from 'react-router-dom'
import ZoneHead from './ZoneHead'
import type { Finding } from '../hooks/useOverviewData'

const SEVERITY_RANK: Record<Finding['severity'], number> = { high: 3, medium: 2, low: 1 }

export default function TrainingQueueTeaser({ findings }: { findings: Finding[] }) {
  const top = findings
    .filter((f) => f.polarity === 'weakness')
    .sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity])
    .slice(0, 3)

  if (top.length === 0) return null

  return (
    <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="Practice next" title="Training queue" />
      <div className="mt-4 flex flex-col gap-2">
        {top.map((f) => (
          <div
            key={f.title}
            data-testid="training-queue-item"
            className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-3"
          >
            <div className="font-condensed text-xs font-semibold text-[var(--cw-text)]">{f.title}</div>
            <div className="mt-0.5 text-xs text-[var(--cw-muted)]">{f.headline}</div>
          </div>
        ))}
      </div>
      <Link
        to="/training?tab=weaknesses"
        className="mt-3 inline-block rounded border border-[var(--cw-copper)] px-3 py-1.5 text-sm text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10"
      >
        Open Training →
      </Link>
    </div>
  )
}

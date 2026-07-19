import { Link } from 'react-router-dom'

export interface BatchFinishedCardProps {
  runId: number
  onDismiss: () => void
}

export default function BatchFinishedCard({ runId, onDismiss }: BatchFinishedCardProps) {
  return (
    <div className="flex items-center justify-between rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
      <div>
        <p className="text-sm text-[var(--cw-text)]">Batch #{runId} finished.</p>
        {/* No runA needed -- the batch-impact page's own default From-
            resolution (previous run relative to runB, or "Start") already
            produces exactly "what did this batch change" with no special
            case here. */}
        <Link to={`/batch-impact?runB=${runId}`} className="mt-1 inline-block text-xs text-[var(--cw-copper)] hover:underline">
          See what changed →
        </Link>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="text-xs text-[var(--cw-muted)] hover:text-[var(--cw-text)]"
      >
        Dismiss
      </button>
    </div>
  )
}

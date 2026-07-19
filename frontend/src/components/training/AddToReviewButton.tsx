import { useNavigate } from 'react-router-dom'
import { useProStatus } from '../../hooks/useProStatus'
import { useAddToReviewDeck } from '../../hooks/useAddToReviewDeck'

export default function AddToReviewButton({
  includeMotifs, includeMoments, includeHoles, topN,
}: { includeMotifs: boolean; includeMoments: boolean; includeHoles: boolean; topN: number }) {
  const proStatus = useProStatus()
  const { addToReview, status, added } = useAddToReviewDeck()
  const navigate = useNavigate()

  if (proStatus.loading || !proStatus.active) return null

  if (status === 'ok') {
    return (
      <button type="button" onClick={() => navigate('/training?tab=review')}
        className="rounded border border-[var(--cw-copper)] bg-[var(--cw-copper)]/10 px-3 py-1.5 text-xs text-[var(--cw-copper)]">
        Added {added} position{added === 1 ? '' : 's'} — go to Review →
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={() => addToReview({ includeMotifs, includeMoments, includeHoles, topN })}
      disabled={status === 'saving'}
      className="rounded border border-[var(--cw-copper)] px-3 py-1.5 text-xs text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10 disabled:opacity-50"
    >
      {status === 'saving' ? 'Adding…' : 'Add to Review deck ✦'}
    </button>
  )
}

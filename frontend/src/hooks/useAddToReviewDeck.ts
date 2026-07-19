import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export type AddToReviewStatus = 'idle' | 'saving' | 'ok' | 'error'

export interface AddToReviewParams {
  includeMotifs: boolean
  includeMoments: boolean
  includeHoles: boolean
  topN: number
}

export interface UseAddToReviewDeckResult {
  addToReview: (params: AddToReviewParams) => void
  status: AddToReviewStatus
  added: number | null
}

export function useAddToReviewDeck(): UseAddToReviewDeckResult {
  const [status, setStatus] = useState<AddToReviewStatus>('idle')
  const [added, setAdded] = useState<number | null>(null)

  function addToReview(params: AddToReviewParams) {
    setStatus('saving')
    fetch(`${API_BASE}/api/training/build-set/add-to-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        include_motifs: params.includeMotifs,
        include_moments: params.includeMoments,
        include_holes: params.includeHoles,
        top_n: params.topN,
      }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ added: number }>
      })
      .then((body) => { setAdded(body.added); setStatus('ok') })
      .catch(() => setStatus('error'))
  }

  return { addToReview, status, added }
}

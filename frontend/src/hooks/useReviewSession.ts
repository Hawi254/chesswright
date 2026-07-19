import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface SrsCard {
  id: number
  fen: string
  source: string
  best_move_san: string
  context: string
  ease_factor: number
  interval_days: number
  repetitions: number
  next_due: string
  added_at: string
  last_reviewed_at: string | null
  actual_move_san: string | null
}

export function useReviewSession() {
  const [queue, setQueue] = useState<SrsCard[] | null>(null)
  const [idx, setIdx] = useState(0)
  const [results, setResults] = useState<number[]>([])

  function start() {
    return fetch(`${API_BASE}/api/training/review/due-cards`)
      .then((r) => r.json() as Promise<SrsCard[]>)
      .then((cards) => {
        setQueue(cards)
        setIdx(0)
        setResults([])
      })
  }

  function rate(cardId: number, rating: number) {
    return fetch(`${API_BASE}/api/training/review/rate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ card_id: cardId, rating }),
    }).then(() => {
      setResults((prev) => [...prev, rating])
      setQueue((prev) => {
        if (!prev) return prev
        // Again (0): re-insert at the end so the card comes back again
        // this session, mirroring chesswright_pro/srs_drills.py's
        // _rate() behavior.
        return rating === 0 ? [...prev, prev[idx]] : prev
      })
      setIdx((prev) => prev + 1)
    })
  }

  function skip(cardId: number) {
    return fetch(`${API_BASE}/api/training/review/skip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ card_id: cardId }),
    }).then(() => {
      setIdx((prev) => prev + 1)
    })
  }

  function reset() {
    setQueue(null)
    setIdx(0)
    setResults([])
  }

  return { queue, idx, results, start, rate, skip, reset }
}

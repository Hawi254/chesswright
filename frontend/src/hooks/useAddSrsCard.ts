import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export type AddSrsCardStatus = 'idle' | 'saving' | 'ok' | 'error'

export interface UseAddSrsCardResult {
  addCard: (fen: string, bestMoveSan: string, context?: string) => void
  status: AddSrsCardStatus
}

export function useAddSrsCard(): UseAddSrsCardResult {
  const [status, setStatus] = useState<AddSrsCardStatus>('idle')

  function addCard(fen: string, bestMoveSan: string, context?: string) {
    setStatus('saving')
    fetch(`${API_BASE}/api/opening-tree/srs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fen, best_move_san: bestMoveSan, context: context ?? null }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        setStatus('ok')
      })
      .catch(() => setStatus('error'))
  }

  return { addCard, status }
}

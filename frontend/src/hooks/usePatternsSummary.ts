import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface TendencyCardData {
  tab_id: string
  label: string
  headline: string
  detail: string
}

export interface UsePatternsSummaryResult {
  cards: TendencyCardData[] | null
  loading: boolean
  error: boolean
}

export function usePatternsSummary(): UsePatternsSummaryResult {
  const [state, setState] = useState<UsePatternsSummaryResult>({ cards: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/patterns/summary`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<TendencyCardData[]>
      })
      .then((cards) => {
        if (!cancelled) setState({ cards, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ cards: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

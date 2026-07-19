import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface NemesisRow {
  opponent_name: string
  n: number
  wins: number
  draws: number
  losses: number
  all_lichess: boolean
  n_rated: number
  score_pct: number
  expected_score_pct: number
  surprise_pct: number
  confidence_tier: 'low' | 'medium' | 'high'
}

export interface UseNemesisOpponentsResult {
  rows: NemesisRow[] | null
  loading: boolean
  error: boolean
}

export function useNemesisOpponents(minGames: number): UseNemesisOpponentsResult {
  const [state, setState] = useState<UseNemesisOpponentsResult>({ rows: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    fetch(`${API_BASE}/api/matchups/nemesis?min_games=${minGames}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<NemesisRow[]>
      })
      .then((rows) => {
        if (!cancelled) setState({ rows, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ rows: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [minGames])

  return state
}

import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface OpeningRow {
  opening_family: string
  player_color: 'white' | 'black'
  n: number
  win_pct: number
  draw_pct: number
  acpl: number | null
  n_analyzed: number
}

export interface UseOpeningsTableResult {
  openings: OpeningRow[] | null
  loading: boolean
  error: boolean
}

export function useOpeningsTable(): UseOpeningsTableResult {
  const [state, setState] = useState<UseOpeningsTableResult>({ openings: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/openings/table`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<OpeningRow[]>
      })
      .then((openings) => {
        if (!cancelled) setState({ openings, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ openings: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

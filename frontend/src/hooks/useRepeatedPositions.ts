import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface RepeatedPositionRow {
  ply: number
  // String, not number -- a 64-bit signed int that routinely exceeds JS's
  // Number.MAX_SAFE_INTEGER; the API round-trips it as an opaque string
  // (see api/main.py's repeated_positions endpoint) to avoid silent
  // precision loss that broke usePositionFen's exact-match lookup.
  zobrist_hash: string
  n_games: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  common_opening: string | null
}

export interface UseRepeatedPositionsResult {
  positions: RepeatedPositionRow[] | null
  loading: boolean
  error: boolean
}

export function useRepeatedPositions(topN: number): UseRepeatedPositionsResult {
  const [state, setState] = useState<UseRepeatedPositionsResult>({ positions: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true }))
    fetch(`${API_BASE}/api/openings/repeated-positions?top_n=${topN}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<RepeatedPositionRow[]>
      })
      .then((positions) => {
        if (!cancelled) setState({ positions, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ positions: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [topN])

  return state
}

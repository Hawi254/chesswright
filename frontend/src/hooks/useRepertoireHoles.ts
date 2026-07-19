import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface RepertoireHoleRow {
  fen_before: string
  n_games: number
  n_distinct_moves: number
  avg_cpl: number | null
  approx_move_number: number
  hole_score: number | null
  most_played_san: string
  opening: string | null
}

export interface UseRepertoireHolesResult {
  holes: RepertoireHoleRow[] | null
  loading: boolean
  error: boolean
}

export function useRepertoireHoles(minAppearances: number, topN: number): UseRepertoireHolesResult {
  const [state, setState] = useState<UseRepertoireHolesResult>({ holes: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true }))
    fetch(`${API_BASE}/api/openings/repertoire-holes?min_appearances=${minAppearances}&top_n=${topN}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<RepertoireHoleRow[]>
      })
      .then((holes) => {
        if (!cancelled) setState({ holes, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ holes: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [minAppearances, topN])

  return state
}

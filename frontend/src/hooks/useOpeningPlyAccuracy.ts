import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface PlyAccuracyRow {
  move_number: number
  n_games: number
  avg_cpl: number
  blunder_rate: number
}

export interface UseOpeningPlyAccuracyResult {
  rows: PlyAccuracyRow[] | null
  loading: boolean
  error: boolean
}

export function useOpeningPlyAccuracy(
  openingFamily: string | null,
  playerColor: string | null,
  minAppearances: number,
): UseOpeningPlyAccuracyResult {
  const [state, setState] = useState<UseOpeningPlyAccuracyResult>({ rows: null, loading: false, error: false })

  useEffect(() => {
    if (!openingFamily || !playerColor) {
      setState({ rows: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState({ rows: null, loading: true, error: false })
    const url = `${API_BASE}/api/openings/ply-accuracy?opening_family=${encodeURIComponent(openingFamily)}`
      + `&player_color=${encodeURIComponent(playerColor)}&min_appearances=${minAppearances}`
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PlyAccuracyRow[]>
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
  }, [openingFamily, playerColor, minAppearances])

  return state
}

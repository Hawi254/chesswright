import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface PhaseAccuracyRow {
  phase: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface DayHourCell {
  day: string
  hour_local: number
  win_pct: number
  rating_diff_display: string
}

export interface DayHourHeatmap {
  cells: DayHourCell[]
  utc_offset_hours: number
}

export interface PatternsGameContextData {
  phase_accuracy: PhaseAccuracyRow[]
  day_hour_heatmap: DayHourHeatmap
}

export interface UsePatternsGameContextResult {
  data: PatternsGameContextData | null
  loading: boolean
  error: boolean
}

export function usePatternsGameContext(): UsePatternsGameContextResult {
  const [state, setState] = useState<UsePatternsGameContextResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/patterns/game-context`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsGameContextData>
      })
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

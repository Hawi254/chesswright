import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface BucketRow {
  bucket: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface TimeControlRow {
  time_control: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface InstantMoveRateRow {
  bucket: string
  n_moves: number
  n_instant: number
  instant_pct: number
}

export interface InstantMoveAccuracy {
  rows: BucketRow[]
  n_analyzed: number
  n_total_in_scope: number
}

export interface PatternsClockTimeData {
  blunder_rate_by_time_pressure: BucketRow[]
  acpl_by_time_control: TimeControlRow[]
  thinking_time_blunder_correlation: BucketRow[]
  instant_move_rate_by_phase: InstantMoveRateRow[]
  instant_move_accuracy: InstantMoveAccuracy
}

export interface UsePatternsClockTimeResult {
  data: PatternsClockTimeData | null
  loading: boolean
  error: boolean
}

export function usePatternsClockTime(): UsePatternsClockTimeResult {
  const [state, setState] = useState<UsePatternsClockTimeResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/patterns/clock-time`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsClockTimeData>
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

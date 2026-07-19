import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface MoveBucketRow {
  bucket: string
  n_losses: number
}

export interface PhaseRow {
  phase: string
  n_losses: number
}

export interface ClockBucketRow {
  bucket: string
  n_losses: number
}

export interface PatternsTurningPointsData {
  n_losses: number
  median_move: number | null
  most_common_phase: string | null
  by_move_bucket: MoveBucketRow[]
  by_phase: PhaseRow[]
  by_clock_bucket: ClockBucketRow[]
  n_no_clock_data: number
}

export interface UsePatternsTurningPointsResult {
  data: PatternsTurningPointsData | null
  loading: boolean
  error: boolean
}

export function usePatternsTurningPoints(): UsePatternsTurningPointsResult {
  const [state, setState] = useState<UsePatternsTurningPointsResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/patterns/turning-points`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsTurningPointsData>
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

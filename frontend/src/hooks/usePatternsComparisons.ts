import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface FavoriteUnderdogWinRow {
  bucket: string
  n_games: number
  win_pct: number
}

export interface FavoriteUnderdogAcplRow {
  bucket: string
  n_games: number
  n_moves: number
  acpl: number
}

export interface ClockPressureByRatingBucketRow {
  rating_bucket: string
  time_bucket: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface OpeningsByRatingBucketRow {
  rating_bucket: string
  opening_family: string
  n_games: number
  win_pct: number
}

export interface ClockPressureByOutcomeRow {
  outcome: string
  time_bucket: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface ClockPressureByColorRow {
  color: string
  time_bucket: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface ClockPressureByOpeningRow {
  opening_family: string
  time_bucket: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface PatternsComparisonsData {
  favorite_underdog: {
    win: FavoriteUnderdogWinRow[]
    acpl: FavoriteUnderdogAcplRow[]
  }
  clock_pressure_by_rating_bucket: ClockPressureByRatingBucketRow[]
  openings_by_rating_bucket: OpeningsByRatingBucketRow[]
  clock_pressure_by_outcome: ClockPressureByOutcomeRow[]
  clock_pressure_by_color: ClockPressureByColorRow[]
  clock_pressure_by_opening: ClockPressureByOpeningRow[]
}

export interface UsePatternsComparisonsResult {
  data: PatternsComparisonsData | null
  loading: boolean
  error: boolean
}

export function usePatternsComparisons(): UsePatternsComparisonsResult {
  const [state, setState] = useState<UsePatternsComparisonsResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/patterns/comparisons`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsComparisonsData>
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

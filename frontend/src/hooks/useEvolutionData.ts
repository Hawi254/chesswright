import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'


export interface RatingPoint {
  year: number
  avg_rating: number
  n_games: number
}

export interface AcplPoint {
  year: number
  acpl: number
  n_games: number
  n_total_games: number
  coverage_pct: number
}

export interface EvolutionData {
  ratingTrajectory: RatingPoint[] | null
  acplTrajectory: AcplPoint[] | null
  loading: boolean
  error: boolean
}

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<T>
}

const EMPTY_STATE: EvolutionData = {
  ratingTrajectory: null,
  acplTrajectory: null,
  loading: true,
  error: false,
}

export function useEvolutionData(): EvolutionData {
  const [state, setState] = useState<EvolutionData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetchJson<RatingPoint[]>('/api/overview/rating-trajectory'),
      fetchJson<AcplPoint[]>('/api/overview/acpl-trajectory'),
    ])
      .then(([ratingTrajectory, acplTrajectory]) => {
        if (!cancelled) {
          setState({ ratingTrajectory, acplTrajectory, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ ...EMPTY_STATE, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

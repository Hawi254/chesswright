import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface FamilyTrendPoint {
  period: number
  label: string
  n_games: number
  n_wins: number
  win_pct: number
}

export interface FamilyAcplPoint {
  label: string
  n_moves: number
  n_games: number
  acpl: number
  n_total_games: number
  coverage_pct: number
}

export interface FamilyDeepDive {
  trend: FamilyTrendPoint[]
  acpl: FamilyAcplPoint[]
}

export interface UseFamilyDeepDiveResult {
  deepDive: FamilyDeepDive | null
  loading: boolean
  error: boolean
}

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<T>
}

export function useFamilyDeepDive(
  family: string | null,
  color: 'white' | 'black',
  timeControl: string | null,
): UseFamilyDeepDiveResult {
  const [state, setState] = useState<UseFamilyDeepDiveResult>({ deepDive: null, loading: false, error: false })

  useEffect(() => {
    if (family === null) {
      setState({ deepDive: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState({ deepDive: null, loading: true, error: false })
    const params = new URLSearchParams({ family, color })
    if (timeControl) params.set('time_control', timeControl)
    const qs = params.toString()

    Promise.all([
      fetchJson<FamilyTrendPoint[]>(`/api/evolution/family-trend?${qs}`),
      fetchJson<FamilyAcplPoint[]>(`/api/evolution/family-acpl?${qs}`),
    ])
      .then(([trend, acpl]) => {
        if (!cancelled) setState({ deepDive: { trend, acpl }, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ deepDive: null, loading: false, error: true })
      })

    return () => {
      cancelled = true
    }
  }, [family, color, timeControl])

  return state
}

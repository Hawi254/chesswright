import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface CompositionShare {
  period: number
  label: string
  family: string
  n_games: number
  share: number
}

export interface LedgerRow {
  family: string
  status: 'adopted' | 'dropped' | 'rising' | 'fading' | 'stable'
  n_games_total: number
  share_early: number
  share_late: number
  win_early: number | null
  win_late: number | null
  n_early: number
  n_late: number
  first_label: string
  last_label: string
  adopted_label: string
  dropped_label: string
}

export interface StripPoint {
  period: number
  label: string
  family: string
  n_games: number
  share: number
}

export interface EvolutionSummary {
  totalGames: number
  nPeriods: number
  composition: { shares: CompositionShare[]; top: string[] }
  ledger: LedgerRow[]
  strips: StripPoint[]
}

interface RawEvolutionSummary {
  total_games: number
  n_periods: number
  composition: { shares: CompositionShare[]; top: string[] }
  ledger: LedgerRow[]
  strips: StripPoint[]
}

export interface UseEvolutionSummaryResult {
  summary: EvolutionSummary | null
  loading: boolean
  error: boolean
}

export function useEvolutionSummary(
  color: 'white' | 'black',
  timeControl: string | null,
  grouping: 'family' | 'eco',
): UseEvolutionSummaryResult {
  const [state, setState] = useState<UseEvolutionSummaryResult>({ summary: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState({ summary: null, loading: true, error: false })
    const params = new URLSearchParams({ color, grouping })
    if (timeControl) params.set('time_control', timeControl)
    fetch(`${API_BASE}/api/evolution/summary?${params.toString()}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<RawEvolutionSummary>
      })
      .then((body) => {
        if (!cancelled) {
          setState({
            summary: {
              totalGames: body.total_games,
              nPeriods: body.n_periods,
              composition: body.composition,
              ledger: body.ledger,
              strips: body.strips,
            },
            loading: false,
            error: false,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setState({ summary: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [color, timeControl, grouping])

  return state
}

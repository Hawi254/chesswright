import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface EndgameMaterialRow {
  endgame_type: string
  n_games: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  acpl: number | null
  blunder_rate: number | null
}

export interface ResignationTrendRow {
  year: number
  quarter: number
  period: number
  label: string
  n_total: number
  n_time_pressure: number
  pct: number | null
}

export interface TimeForfeitTrendRow {
  year: number
  quarter: number
  period: number
  label: string
  n_total: number
  n_ahead: number
  n_mutual: number
  pct_ahead: number | null
  pct_mutual: number | null
}

export interface EndingSummary {
  hero: {
    total_games: number
    decisive_pct: number | null
    draw_pct: number | null
    resignation_explained_pct: number | null
    flagged_while_ahead_pct: number | null
  }
  endgame_material: EndgameMaterialRow[]
  resignation_trend: ResignationTrendRow[]
  time_forfeit_trend: TimeForfeitTrendRow[]
}

export interface UseEndingSummaryResult {
  summary: EndingSummary | null
  loading: boolean
  error: boolean
}

export function useEndingSummary(): UseEndingSummaryResult {
  const [state, setState] = useState<UseEndingSummaryResult>({ summary: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/game-endings/summary`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<EndingSummary>
      })
      .then((summary) => {
        if (!cancelled) setState({ summary, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ summary: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

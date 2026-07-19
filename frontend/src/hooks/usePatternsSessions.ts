import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface SessionRollupRow {
  session_start: string
  session_end: string
  n_games: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  acpl: number | null
  n_analyzed: number
}

export interface PriorOutcomeRow {
  bucket: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface SessionPositionRow {
  position: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface EventTypeRow {
  category: string
  n_games: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  acpl: number | null
  n_analyzed: number
}

export interface EventNameBreakdownRow {
  event: string
  n_games: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  acpl: number | null
  n_analyzed: number
}

export interface PatternsSessionsData {
  session_rollup: SessionRollupRow[]
  prior_outcome: PriorOutcomeRow[]
  session_position: SessionPositionRow[]
  event_type: EventTypeRow[]
  event_name_breakdown: EventNameBreakdownRow[]
}

export interface UsePatternsSessionsResult {
  data: PatternsSessionsData | null
  loading: boolean
  error: boolean
}

export function usePatternsSessions(): UsePatternsSessionsResult {
  const [state, setState] = useState<UsePatternsSessionsResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/patterns/sessions`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsSessionsData>
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

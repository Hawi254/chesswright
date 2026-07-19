import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface TimelineSummary {
  split_year: number
  before_san: string
  before_n: number
  before_total: number
  before_share: number
  before_win_pct: number
  before_cpl: number | null
  after_san: string
  after_n: number
  after_total: number
  after_share: number
  after_win_pct: number
  after_cpl: number | null
}

export interface TimelineRow {
  san: string
  year: number
  is_player_move: boolean
  n_games: number
  n_wins: number
  n_draws: number
  n_losses: number
  cpl_sum: number | null
  cpl_n: number
}

export interface UseOpeningPositionTimelineResult {
  summary: TimelineSummary | null
  rows: TimelineRow[]
  loading: boolean
  error: boolean
}

export function useOpeningPositionTimeline(fen: string | null, color: 'w' | 'b'): UseOpeningPositionTimelineResult {
  const [state, setState] = useState<UseOpeningPositionTimelineResult>({ summary: null, rows: [], loading: true, error: false })

  useEffect(() => {
    if (!fen) {
      setState({ summary: null, rows: [], loading: false, error: false })
      return
    }
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    fetch(`${API_BASE}/api/opening-tree/timeline?fen=${encodeURIComponent(fen)}&color=${color}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ summary: TimelineSummary | null; rows: TimelineRow[] }>
      })
      .then((body) => {
        if (!cancelled) setState({ summary: body.summary, rows: body.rows, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ summary: null, rows: [], loading: false, error: true })
      })
    return () => { cancelled = true }
  }, [fen, color])

  return state
}

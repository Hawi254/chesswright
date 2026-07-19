import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface WinRateByRatingDiffRow { band: number; n: number; win_pct: number }
export interface ColorPerformanceRow { rating_bucket: string; black: number | null; white: number | null }
export interface GiantKillingCounts {
  n_upsets: number; n_underdog_games: number; n_collapses: number; n_favorite_games: number
}
export interface CollapseReasonRow { reason: string; n: number; pct: number }
export interface CollapsePieceRow { hung_piece: string; n: number; pct: number; piece_name: string }
export interface CollapseMateRow { bucket: string; n: number; pct: number }
export interface GiantKillingTrendRow {
  year: number; quarter: number; period: string; label: string
  n_underdog: number; n_upset: number; pct_upset: number | null
  n_favorite: number; n_collapse: number; pct_collapse: number | null
}
export interface ComebackCollapseCounts {
  n_comebacks: number; n_collapses: number; comeback_game_ids: string[]; collapse_game_ids: string[]
}

export interface MatchupsRatingFormData {
  win_rate_by_rating_diff: WinRateByRatingDiffRow[]
  color_performance_by_rating: ColorPerformanceRow[]
  giant_killing_counts: GiantKillingCounts
  collapse_causes: { reason: CollapseReasonRow[]; piece: CollapsePieceRow[]; mate: CollapseMateRow[] }
  giant_killing_rate_trend: GiantKillingTrendRow[]
  comeback_collapse: ComebackCollapseCounts
}

export interface UseMatchupsRatingFormResult {
  data: MatchupsRatingFormData | null
  loading: boolean
  error: boolean
}

export function useMatchupsRatingForm(): UseMatchupsRatingFormResult {
  const [state, setState] = useState<UseMatchupsRatingFormResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/matchups/rating-form`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<MatchupsRatingFormData>
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

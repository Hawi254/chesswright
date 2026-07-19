import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { PointsBucketKey } from '../lib/pointsLabels'

export interface PointsBucketSummary { bucket: PointsBucketKey; n_games: number; leaked: number }
export interface PointsMonthlyRow { month: string; n_games: number; actual_pct: number; potential_pct: number }
export interface PointsAdvBandRow { adv_band: string; n_games: number; leaked: number }
export interface PointsConvPhaseRow { conv_phase: string; n_games: number; leaked: number }
export interface PointsConvClockRow { conv_clock: string; n_games: number; leaked: number }
export interface PointsReasonRow { reason: string; n: number; pct: number }
export interface PointsLabeledRow { label: string; n: number; pct: number }
export interface PointsCostliestGame {
  game_id: string
  utc_date: string
  opponent_name: string
  outcome_for_player: string
  bucket: PointsBucketKey
  best_chance: number
  leaked: number
  url: string | null
}

export interface PointsSummary {
  tc_options: string[]
  n_games: number
  actual_pct: number
  leaked_points: number
  ceiling_pct: number
  buckets: PointsBucketSummary[]
  monthly: PointsMonthlyRow[]
  conversion_breakdown: {
    adv_band: PointsAdvBandRow[]
    conv_phase: PointsConvPhaseRow[]
    conv_clock: PointsConvClockRow[]
  }
  causes: { reason: PointsReasonRow[]; piece: PointsLabeledRow[]; mate: PointsLabeledRow[] }
  costliest_games: PointsCostliestGame[]
  analyzed_games: number | null
}

export interface UsePointsLedgerResult {
  summary: PointsSummary | null
  loading: boolean
  error: boolean
}

export function usePointsLedger(timeControl: string | null): UsePointsLedgerResult {
  const [state, setState] = useState<UsePointsLedgerResult>({ summary: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    const query = timeControl ? `?time_control=${timeControl}` : ''
    fetch(`${API_BASE}/api/points/summary${query}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PointsSummary>
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
  }, [timeControl])

  return state
}

import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { Finding, HeadlineStats, RatingSnapshot } from './useOverviewData'

export interface HeadlineTrend {
  compared_to_date: string | null
  acpl_delta: number | null
  blunder_rate_delta: number | null
  win_pct_delta: number | null
  implied_rating_delta: number | null
}

export interface InsightsData {
  stats: HeadlineStats | null
  findings: Finding[] | null
  ratingSnapshot: RatingSnapshot | null
  trend: HeadlineTrend | null
  loading: boolean
  error: boolean
}

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<T>
}

const EMPTY_STATE: InsightsData = {
  stats: null,
  findings: null,
  ratingSnapshot: null,
  trend: null,
  loading: true,
  error: false,
}

export function useInsightsData(): InsightsData {
  const [state, setState] = useState<InsightsData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetchJson<HeadlineStats>('/api/overview/headline-stats'),
      fetchJson<Finding[]>('/api/overview/career-findings'),
      fetchJson<RatingSnapshot>('/api/overview/rating-snapshot'),
      fetchJson<HeadlineTrend>('/api/overview/headline-trend'),
    ])
      .then(([stats, findings, ratingSnapshot, trend]) => {
        if (!cancelled) setState({ stats, findings, ratingSnapshot, trend, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ ...EMPTY_STATE, loading: false, error: true })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

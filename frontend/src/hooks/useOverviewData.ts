import { useEffect, useState } from 'react'

const API_BASE = 'http://127.0.0.1:8123'

export interface HeadlineStats {
  total_games: number
  analyzed_games: number
  acpl: number | null
  blunder_rate: number | null
  win_pct: number | null
  n_analyzed_moves: number
}

export interface RatingSnapshot {
  current_rating: number | null
  peak_rating: number | null
}

export interface Streak {
  outcome: string | null
  length: number
}

export interface Finding {
  title: string
  headline: string
  detail: string
  polarity: 'strength' | 'weakness' | 'mixed' | 'neutral'
  severity: 'low' | 'medium' | 'high'
  category: 'tactical' | 'time' | 'defense' | 'matchup' | 'giant_killer' | 'general'
  confidence?: 'insufficient' | 'low' | 'medium' | 'high'
}

export interface OverviewData {
  stats: HeadlineStats | null
  ratingSnapshot: RatingSnapshot | null
  streak: Streak | null
  findings: Finding[] | null
  narrative: string | null
  loading: boolean
  error: boolean
}

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<T>
}

const EMPTY_STATE: OverviewData = {
  stats: null,
  ratingSnapshot: null,
  streak: null,
  findings: null,
  narrative: null,
  loading: true,
  error: false,
}

export function useOverviewData(): OverviewData {
  const [state, setState] = useState<OverviewData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetchJson<HeadlineStats>('/api/overview/headline-stats'),
      fetchJson<RatingSnapshot>('/api/overview/rating-snapshot'),
      fetchJson<Streak>('/api/overview/current-streak'),
      fetchJson<Finding[]>('/api/overview/career-findings'),
      fetchJson<{ narrative: string }>('/api/overview/narrative'),
    ])
      .then(([stats, ratingSnapshot, streak, findings, narrativeResp]) => {
        if (!cancelled) {
          setState({
            stats,
            ratingSnapshot,
            streak,
            findings,
            narrative: narrativeResp.narrative,
            loading: false,
            error: false,
          })
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

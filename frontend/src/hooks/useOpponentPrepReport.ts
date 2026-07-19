import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface RepertoireRow {
  color: 'white' | 'black'
  opening: string
  n_games: number
  score_pct: number
  avg_cpl: number | null
  blunder_pct: number | null
}

export interface OpponentPrepReport {
  gamesAnalyzed: number
  colorSplit: { white: number; black: number }
  dateRange: { from: string | null; to: string | null }
  repertoire: RepertoireRow[]
}

export interface UseOpponentPrepReportResult {
  report: OpponentPrepReport | null
  loading: boolean
  error: boolean
}

export function useOpponentPrepReport(username: string | null): UseOpponentPrepReportResult {
  const [report, setReport] = useState<OpponentPrepReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!username) {
      setReport(null)
      setLoading(false)
      setError(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(false)
    fetch(`${API_BASE}/api/opponent-prep/report/${encodeURIComponent(username)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<OpponentPrepReport>
      })
      .then((body) => {
        if (cancelled) return
        setReport(body)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setReport(null)
        setLoading(false)
        setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [username])

  return { report, loading, error }
}

export interface UseOpponentPrepOpponentsResult {
  opponents: string[]
  loading: boolean
}

export function useOpponentPrepOpponents(): UseOpponentPrepOpponentsResult {
  const [opponents, setOpponents] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/opponent-prep/list`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ opponents: string[] }>
      })
      .then((body) => {
        if (cancelled) return
        setOpponents(body.opponents)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setOpponents([])
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { opponents, loading }
}

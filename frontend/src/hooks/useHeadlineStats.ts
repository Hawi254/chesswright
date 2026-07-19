import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { HeadlineStats } from './useOverviewData'

export interface UseHeadlineStatsResult {
  stats: HeadlineStats | null
  loading: boolean
  error: boolean
}

export function useHeadlineStats(): UseHeadlineStatsResult {
  const [stats, setStats] = useState<HeadlineStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/overview/headline-stats`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<HeadlineStats>
      })
      .then((body) => {
        if (cancelled) return
        setStats(body)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { stats, loading, error }
}

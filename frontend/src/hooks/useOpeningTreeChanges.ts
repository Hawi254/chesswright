import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface OpeningChange {
  ply: number
  zobrist_hash: string
  path: string[] | null
  before_san: string
  before_share: number
  before_win_pct: number
  before_total: number
  after_san: string
  after_share: number
  after_win_pct: number
  after_total: number
}

export interface UseOpeningTreeChangesResult {
  changes: OpeningChange[]
  loading: boolean
  error: boolean
}

export function useOpeningTreeChanges(color: 'w' | 'b', minGames: number): UseOpeningTreeChangesResult {
  const [state, setState] = useState<UseOpeningTreeChangesResult>({ changes: [], loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    fetch(`${API_BASE}/api/opening-tree/changes?color=${color}&min_games=${minGames}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<OpeningChange[]>
      })
      .then((changes) => {
        if (!cancelled) setState({ changes, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ changes: [], loading: false, error: true })
      })
    return () => { cancelled = true }
  }, [color, minGames])

  return state
}

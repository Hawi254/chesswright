import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { EndingTree } from '../lib/endingTree'

export interface UseEndingTreeResult {
  tree: EndingTree | null
  loading: boolean
  error: boolean
}

export function useEndingTree(timeControl: string | null): UseEndingTreeResult {
  const [state, setState] = useState<UseEndingTreeResult>({ tree: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    const query = timeControl ? `?time_control=${timeControl}` : ''
    fetch(`${API_BASE}/api/game-endings/tree${query}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<EndingTree>
      })
      .then((tree) => {
        if (!cancelled) setState({ tree, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ tree: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [timeControl])

  return state
}

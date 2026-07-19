import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { OpeningTreeMap } from '../lib/openingTreeMap'

export interface UseOpeningTreeMapResult {
  map: OpeningTreeMap | null
  loading: boolean
  error: boolean
}

export function useOpeningTreeMap(color: 'w' | 'b', minGames: number, enabled = true): UseOpeningTreeMapResult {
  const [state, setState] = useState<UseOpeningTreeMapResult>({ map: null, loading: true, error: false })

  useEffect(() => {
    if (!enabled) {
      setState({ map: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    fetch(`${API_BASE}/api/opening-tree/map?color=${color}&min_games=${minGames}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<OpeningTreeMap>
      })
      .then((map) => {
        if (!cancelled) setState({ map, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ map: null, loading: false, error: true })
      })
    return () => { cancelled = true }
  }, [color, minGames, enabled])

  return state
}

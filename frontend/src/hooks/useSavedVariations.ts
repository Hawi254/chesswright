import { useCallback, useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface SavedVariation {
  id: string
  game_id: string
  branch_ply: number
  branch_fen: string
  moves: string[]
  title: string | null
  created_at: string
  updated_at: string
}

export interface UseSavedVariationsResult {
  variations: SavedVariation[]
  loading: boolean
  refetch: () => void
}

export function useSavedVariations(gameId: string | null): UseSavedVariationsResult {
  const [variations, setVariations] = useState<SavedVariation[]>([])
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    if (!gameId) return
    let cancelled = false
    setLoading(true)

    fetch(`${API_BASE}/api/games/${gameId}/variations`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<SavedVariation[]>
      })
      .then((body) => {
        if (cancelled) return
        setVariations(body)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setVariations([])
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [gameId, reloadToken])

  const refetch = useCallback(() => setReloadToken((t) => t + 1), [])

  return { variations, loading, refetch }
}

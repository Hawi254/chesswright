import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UsePositionFenResult {
  fen: string | null
  loading: boolean
  error: boolean
}

export function usePositionFen(ply: number | null, zobristHash: string | null): UsePositionFenResult {
  const [state, setState] = useState<UsePositionFenResult>({ fen: null, loading: false, error: false })

  useEffect(() => {
    if (ply === null || zobristHash === null) {
      setState({ fen: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState({ fen: null, loading: true, error: false })
    fetch(`${API_BASE}/api/openings/position-fen?ply=${ply}&zobrist_hash=${zobristHash}`)
      .then((r): Promise<{ fen: string | null }> => {
        if (r.status === 404) return Promise.resolve({ fen: null })
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ fen: string }>
      })
      .then((body) => {
        if (cancelled) return
        setState({ fen: body.fen, loading: false, error: false })
      })
      .catch(() => {
        if (cancelled) return
        setState({ fen: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [ply, zobristHash])

  return state
}

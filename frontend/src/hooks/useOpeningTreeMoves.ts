import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface OpeningMove {
  san: string
  is_player_move: boolean
  n_games: number
  n_wins: number
  n_draws: number
  n_losses: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  avg_cpl: number | null
}

export interface UseOpeningTreeMovesResult {
  moves: OpeningMove[]
  loading: boolean
  error: boolean
}

export function useOpeningTreeMoves(
  fen: string | null, ply: number, color: 'w' | 'b', minGames: number,
): UseOpeningTreeMovesResult {
  const [state, setState] = useState<UseOpeningTreeMovesResult>({ moves: [], loading: true, error: false })

  useEffect(() => {
    if (!fen) {
      setState({ moves: [], loading: false, error: false })
      return
    }
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true, error: false }))
    fetch(`${API_BASE}/api/opening-tree/moves?fen=${encodeURIComponent(fen)}&ply=${ply}&color=${color}&min_games=${minGames}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<OpeningMove[]>
      })
      .then((moves) => {
        if (!cancelled) setState({ moves, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ moves: [], loading: false, error: true })
      })
    return () => { cancelled = true }
  }, [fen, ply, color, minGames])

  return state
}

import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface OpeningProfileRow { opening_family: string; n_games: number; win_pct: number; acpl: number | null }
export interface PositionProfileRow { bucket: string; n_games: number; win_pct: number }
export interface CastlingProfileRow { castling_config: string; n_games: number; win_pct: number }
export interface ActionSideProfileRow { action_side: string; n_games: number; win_pct: number }
export interface ClockProfileRow { bucket: string; n_moves: number; acpl: number | null; blunder_rate: number | null }

export interface OpponentProfile {
  n_games: number
  openings: OpeningProfileRow[]
  position: PositionProfileRow[]
  castling: CastlingProfileRow[]
  action_side: ActionSideProfileRow[]
  clock: ClockProfileRow[]
}

export interface UseOpponentProfileResult {
  profile: OpponentProfile | null
  loading: boolean
  error: boolean
}

export function useOpponentProfile(opponentName: string | null): UseOpponentProfileResult {
  const [state, setState] = useState<UseOpponentProfileResult>({ profile: null, loading: false, error: false })

  useEffect(() => {
    if (!opponentName) {
      setState({ profile: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState({ profile: null, loading: true, error: false })
    fetch(`${API_BASE}/api/matchups/opponent-profile?opponent_name=${encodeURIComponent(opponentName)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<OpponentProfile>
      })
      .then((profile) => {
        if (!cancelled) setState({ profile, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ profile: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [opponentName])

  return state
}

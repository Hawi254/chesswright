import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { BadgeFlags } from '../lib/badges'

export interface ExplorerGame extends BadgeFlags {
  game_id: string
  utc_date: string
  opponent_name: string
  opponent_rating: number
  player_color: 'white' | 'black'
  outcome_for_player: 'win' | 'loss' | 'draw'
  time_control_category: string
  opening_family: string
  rating_diff: number
  site: string
  analysis_status: string
  badge_count: number
  drama_score: number
  lichess_url: string
  platform: 'Lichess' | 'Chess.com'
}

export interface GameExplorerData {
  games: ExplorerGame[] | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: GameExplorerData = { games: null, loading: true, error: false }

export function useGameExplorer(): GameExplorerData {
  const [state, setState] = useState<GameExplorerData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/games/explorer`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<ExplorerGame[]>
      })
      .then((games) => {
        if (!cancelled) setState({ games, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ games: null, loading: false, error: true })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

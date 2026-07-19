import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import type { BadgeFlags } from '../lib/badges'

export interface GameDetailHeader extends BadgeFlags {
  game_id: string
  utc_date: string
  opponent_name: string
  opponent_rating: number
  player_rating: number
  player_color: 'white' | 'black'
  outcome_for_player: 'win' | 'loss' | 'draw'
  time_control_category: string
  opening_family: string
  rating_diff: number
  game_end_type: string
  analysis_status: string
  last_analyzed_ply: number | null
  site: string
  lichess_url: string
}

export interface GameDetailMove {
  ply: number
  san: string
  is_player_move: number
  classification: string | null
  cpl: number | null
  sharpness: number | null
  is_brilliant_candidate: boolean
  is_puzzle_trigger: boolean
  fen_before: string
  fen_after: string
  win_prob_before: number | null
  win_prob_after: number | null
  motif: string | null
}

export interface WinProbPoint {
  ply: number
  player_win_prob: number
}

export interface GameDetailData {
  header: GameDetailHeader | null
  moves: GameDetailMove[] | null
  winProb: WinProbPoint[] | null
  loading: boolean
  error: boolean
  notFound: boolean
}

const EMPTY_STATE: GameDetailData = {
  header: null,
  moves: null,
  winProb: null,
  loading: true,
  error: false,
  notFound: false,
}

interface GameDetailResponse {
  header: GameDetailHeader
  moves: GameDetailMove[]
  win_prob: WinProbPoint[]
}

export function useGameDetail(gameId: string | null): GameDetailData {
  const [state, setState] = useState<GameDetailData>(EMPTY_STATE)

  useEffect(() => {
    if (!gameId) return
    let cancelled = false
    setState(EMPTY_STATE)

    fetch(`${API_BASE}/api/games/${gameId}`)
      .then((r) => {
        if (r.status === 404) return null
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<GameDetailResponse>
      })
      .then((body) => {
        if (cancelled) return
        if (body === null) {
          setState({ ...EMPTY_STATE, loading: false, notFound: true })
          return
        }
        setState({
          header: body.header,
          moves: body.moves,
          winProb: body.win_prob,
          loading: false,
          error: false,
          notFound: false,
        })
      })
      .catch(() => {
        if (!cancelled) setState({ ...EMPTY_STATE, loading: false, error: true })
      })

    return () => {
      cancelled = true
    }
  }, [gameId])

  return state
}

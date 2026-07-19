import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'


export interface CareerHighlightGame {
  game_id: string
  opponent_name: string
  utc_date: string
  outcome_for_player: 'win' | 'loss' | 'draw'
  is_comeback: boolean
  is_giant_killing: boolean
  is_brilliant_find: boolean
  is_blunder_fest: boolean
  is_nail_biter: boolean
}

export interface CareerHighlightData {
  games: CareerHighlightGame[] | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: CareerHighlightData = {
  games: null,
  loading: true,
  error: false,
}

export function useCareerHighlight(): CareerHighlightData {
  const [state, setState] = useState<CareerHighlightData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/overview/career-highlight`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<CareerHighlightGame[]>
      })
      .then((games) => {
        if (!cancelled) {
          setState({ games, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ games: null, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

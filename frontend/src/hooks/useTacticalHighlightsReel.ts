import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export type HighlightCategory =
  | 'brilliant' | 'puzzle_conversion' | 'best_move_streak' | 'blown_mate' | 'great_escape'

export interface HighlightMoment {
  game_id: string
  category: HighlightCategory
  move_number: number
  san: string
  magnitude: number
  magnitude_label: string
  strength: number
  caption: string
  opponent_name: string | null
  utc_date: string | null
  outcome_for_player: 'win' | 'loss' | 'draw' | null
  player_color: 'white' | 'black' | null
  fen: string | null
  lastmove_from: string | null
  lastmove_to: string | null
}

export type HighlightCounts = Record<HighlightCategory, number>

export interface HighlightReelData {
  moments: HighlightMoment[] | null
  counts: HighlightCounts | null
  loading: boolean
  error: boolean
}

interface ReelResponse {
  moments: HighlightMoment[]
  counts: HighlightCounts
}

const EMPTY_STATE: HighlightReelData = {
  moments: null,
  counts: null,
  loading: true,
  error: false,
}

export function useTacticalHighlightsReel(): HighlightReelData {
  const [state, setState] = useState<HighlightReelData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/tactical-highlights/reel`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<ReelResponse>
      })
      .then((body) => {
        if (!cancelled) {
          setState({ moments: body.moments, counts: body.counts, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ moments: null, counts: null, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

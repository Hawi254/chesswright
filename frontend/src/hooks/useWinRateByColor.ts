import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'


export interface WinRateByColorRow {
  player_color: 'white' | 'black'
  n: number
  win_pct: number
  draw_pct: number
}

export interface WinRateByColorData {
  rows: WinRateByColorRow[] | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: WinRateByColorData = {
  rows: null,
  loading: true,
  error: false,
}

export function useWinRateByColor(): WinRateByColorData {
  const [state, setState] = useState<WinRateByColorData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/overview/win-rate-by-color`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<WinRateByColorRow[]>
      })
      .then((rows) => {
        if (!cancelled) {
          setState({ rows, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ rows: null, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

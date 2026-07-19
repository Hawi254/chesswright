import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface SwindleRate { n_losses: number; n_missed_swindle: number; swindle_rate_pct: number | null }

export interface UseOpponentSwindleRateResult {
  swindle: SwindleRate | null
  loading: boolean
  error: boolean
}

export function useOpponentSwindleRate(opponentName: string | null): UseOpponentSwindleRateResult {
  const [state, setState] = useState<UseOpponentSwindleRateResult>({ swindle: null, loading: false, error: false })

  useEffect(() => {
    if (!opponentName) {
      setState({ swindle: null, loading: false, error: false })
      return
    }
    let cancelled = false
    setState({ swindle: null, loading: true, error: false })
    fetch(`${API_BASE}/api/matchups/opponent-swindle-rate?opponent_name=${encodeURIComponent(opponentName)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<SwindleRate>
      })
      .then((swindle) => {
        if (!cancelled) setState({ swindle, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ swindle: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [opponentName])

  return state
}

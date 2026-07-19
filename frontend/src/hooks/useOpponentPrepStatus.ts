import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export type OpponentPrepStatusValue = 'idle' | 'starting' | 'running' | 'stopping' | 'error' | 'done'

export interface OpponentPrepStatus {
  status: OpponentPrepStatusValue
  username: string | null
  step: string | null
  error: string | null
}

export interface UseOpponentPrepStatusResult {
  data: OpponentPrepStatus | null
  loading: boolean
  connectionLost: boolean
}

const POLL_INTERVAL_MS = 2000

export function useOpponentPrepStatus(): UseOpponentPrepStatusResult {
  const [data, setData] = useState<OpponentPrepStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [connectionLost, setConnectionLost] = useState(false)

  useEffect(() => {
    let cancelled = false

    function poll() {
      fetch(`${API_BASE}/api/opponent-prep/status`)
        .then((r) => {
          if (!r.ok) throw new Error(`status ${r.status}`)
          return r.json() as Promise<OpponentPrepStatus>
        })
        .then((body) => {
          if (cancelled) return
          setData(body)
          setLoading(false)
          setConnectionLost(false)
        })
        .catch(() => {
          if (cancelled) return
          setLoading(false)
          setConnectionLost(true)
        })
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return { data, loading, connectionLost }
}

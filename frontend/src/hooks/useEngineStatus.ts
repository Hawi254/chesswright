import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'


export interface EngineStatusData {
  connected: boolean | null
  version: string | null
  appVersion: string | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: EngineStatusData = {
  connected: null,
  version: null,
  appVersion: null,
  loading: true,
  error: false,
}

export function useEngineStatus(): EngineStatusData {
  const [state, setState] = useState<EngineStatusData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/overview/engine-status`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ connected: boolean; version: string | null; app_version: string }>
      })
      .then((body) => {
        if (!cancelled) {
          setState({
            connected: body.connected,
            version: body.version,
            appVersion: body.app_version,
            loading: false,
            error: false,
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ ...EMPTY_STATE, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

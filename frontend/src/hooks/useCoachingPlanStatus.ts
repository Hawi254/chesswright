import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'


export interface CoachingPlanStatusData {
  cached: boolean | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: CoachingPlanStatusData = {
  cached: null,
  loading: true,
  error: false,
}

export function useCoachingPlanStatus(): CoachingPlanStatusData {
  const [state, setState] = useState<CoachingPlanStatusData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/overview/coaching-plan-status`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ cached: boolean }>
      })
      .then((body) => {
        if (!cancelled) {
          setState({ cached: body.cached, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ cached: null, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'


export interface Milestone {
  achievement_id: string
  name: string
  description: string
  unlocked_at: string
}

export interface MilestonesData {
  milestones: Milestone[] | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: MilestonesData = {
  milestones: null,
  loading: true,
  error: false,
}

export function useMilestones(): MilestonesData {
  const [state, setState] = useState<MilestonesData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/overview/achievements`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<Milestone[]>
      })
      .then((milestones) => {
        if (!cancelled) {
          setState({ milestones, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ milestones: null, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}

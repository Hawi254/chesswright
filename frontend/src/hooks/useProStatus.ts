import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseProStatusResult {
  active: boolean
  loading: boolean
}

export function useProStatus(): UseProStatusResult {
  const [active, setActive] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/pro-status`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ active: boolean }>
      })
      .then((body) => {
        if (cancelled) return
        setActive(body.active)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setActive(false)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { active, loading }
}

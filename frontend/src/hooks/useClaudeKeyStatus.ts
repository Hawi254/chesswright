import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseClaudeKeyStatusResult {
  available: boolean
}

export function useClaudeKeyStatus(): UseClaudeKeyStatusResult {
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/settings/claude-key-status`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ available: boolean }>
      })
      .then((body) => {
        if (cancelled) return
        setAvailable(body.available)
      })
      .catch(() => {
        if (cancelled) return
        setAvailable(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { available }
}

import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export type OpeningJumpStatus = 'idle' | 'loading' | 'ok' | 'not_found' | 'error'

export interface UseOpeningJumpResult {
  jump: (openingFamily: string) => void
  path: string[] | null
  status: OpeningJumpStatus
}

export function useOpeningJump(color: 'w' | 'b'): UseOpeningJumpResult {
  const [path, setPath] = useState<string[] | null>(null)
  const [status, setStatus] = useState<OpeningJumpStatus>('idle')

  function jump(openingFamily: string) {
    setStatus('loading')
    fetch(`${API_BASE}/api/opening-tree/jump?opening_family=${encodeURIComponent(openingFamily)}&color=${color}`)
      .then((r) => {
        if (r.status === 404) {
          setStatus('not_found')
          setPath(null)
          return null
        }
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ path: string[] }>
      })
      .then((body) => {
        if (body) {
          setPath(body.path)
          setStatus('ok')
        }
      })
      .catch(() => {
        setStatus('error')
        setPath(null)
      })
  }

  return { jump, path, status }
}

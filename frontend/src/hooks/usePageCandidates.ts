import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import { STATIC_CANDIDATES, type PageCandidate } from '../lib/navCandidates'


export interface UsePageCandidatesResult {
  candidates: PageCandidate[]
  usingFallback: boolean
}

export function usePageCandidates(): UsePageCandidatesResult {
  const [candidates, setCandidates] = useState<PageCandidate[]>(STATIC_CANDIDATES)
  const [usingFallback, setUsingFallback] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/nav/pages`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PageCandidate[]>
      })
      .then((data) => {
        if (!cancelled) {
          setCandidates(data)
          setUsingFallback(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          console.warn(
            'Chesswright: /api/nav/pages unreachable, using the bundled static nav list.',
          )
          setCandidates(STATIC_CANDIDATES)
          setUsingFallback(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { candidates, usingFallback }
}

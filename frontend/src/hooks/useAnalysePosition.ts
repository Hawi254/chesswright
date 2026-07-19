import { useRef, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface AnalysisResult {
  eval_cp: number | null
  eval_mate: number | null
  best_move_san: string | null
  best_move_from: string | null
  best_move_to: string | null
  pv: string[]
  depth: number | null
  source: 'stored' | 'cached' | 'lichess_cloud' | 'live'
}

export type AnalysisStatus = 'idle' | 'ok' | 'no_engine' | 'batch_running' | 'analysis_failed' | 'error'

interface AnalysePositionResponse {
  status: Exclude<AnalysisStatus, 'idle' | 'error'>
  result: AnalysisResult | null
}

export interface UseAnalysePositionResult {
  analyse: (fen: string) => void
  result: AnalysisResult | null
  resultFen: string | null
  status: AnalysisStatus
  loading: boolean
}

export function useAnalysePosition(): UseAnalysePositionResult {
  const [cache, setCache] = useState<Record<string, AnalysisResult>>({})
  const [status, setStatus] = useState<AnalysisStatus>('idle')
  const [loading, setLoading] = useState(false)
  const [activeFen, setActiveFen] = useState<string | null>(null)
  // Not a "cancelled" flag (this hook has no useEffect to clean up) --
  // tracks which analyse() call is the most recent, so a slow response to
  // an earlier call can't clobber a faster response to a later one.
  const latestFenRef = useRef<string | null>(null)

  function analyse(fen: string) {
    setActiveFen(fen)
    latestFenRef.current = fen

    if (cache[fen]) {
      setStatus('ok')
      setLoading(false)
      return
    }

    setLoading(true)
    setStatus('idle')

    fetch(`${API_BASE}/api/analyse-position`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fen }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<AnalysePositionResponse>
      })
      .then((body) => {
        if (latestFenRef.current !== fen) return
        setLoading(false)
        setStatus(body.status)
        if (body.status === 'ok' && body.result) {
          const result = body.result
          setCache((prev) => ({ ...prev, [fen]: result }))
        }
      })
      .catch(() => {
        if (latestFenRef.current !== fen) return
        setLoading(false)
        setStatus('error')
      })
  }

  const result = activeFen ? (cache[activeFen] ?? null) : null
  return { analyse, result, resultFen: result ? activeFen : null, status, loading }
}

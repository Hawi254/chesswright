import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface BatchImpactRun { id: number; label: string; gamesAnalyzed: number; endedAt: string | null }
export interface BatchImpactCounter { totalBatches: number; totalGamesAnalyzed: number }
export interface BatchImpactRange { runA: number | null; runB: number | null }
export interface BatchImpactHeadline {
  gamesInRange: number
  acplBefore: number | null; acplAfter: number
  blunderRateBefore: number | null; blunderRateAfter: number
  newBlunders: number; newBrilliant: number
  topMotif: string | null; topMotifCount: number
}
export interface BatchImpactRecord { runId: number; label: string; metric: 'acpl' | 'blunder_rate'; value: number; priorBest: number | null }
export interface BatchImpactTrendRow {
  runId: number; endedAt: string | null; gamesAnalyzed: number
  cumulativeAcpl: number | null; cumulativeBlunderRate: number | null
}
export interface BatchImpactPhaseRow {
  phase: string; acplBefore: number | null; acplAfter: number | null
  blunderRateBefore: number | null; blunderRateAfter: number | null; nMovesInRange: number
}
export interface BatchImpactEndgameRow {
  endgameType: string; acplBefore: number | null; acplAfter: number | null
  blunderRateBefore: number | null; blunderRateAfter: number | null; nMovesInRange: number
}
export interface BatchImpactMotifRow { motif: string; before: number; after: number; delta: number }
export interface BatchImpactBlunder { gameId: string; ply: number; san: string; cpl: number; motif: string | null }

export interface BatchImpactSummary {
  runs: BatchImpactRun[]
  counter: BatchImpactCounter
  range: BatchImpactRange
  pendingAnnotation: boolean
  headline: BatchImpactHeadline | null
  records: BatchImpactRecord[]
  trend: BatchImpactTrendRow[]
  phase: BatchImpactPhaseRow[]
  endgame: BatchImpactEndgameRow[]
  motifs: BatchImpactMotifRow[]
  newBlunders: BatchImpactBlunder[]
}

export interface UseBatchImpactResult {
  summary: BatchImpactSummary | null
  loading: boolean
  error: boolean
  blocked: boolean
}

export function useBatchImpact(
  runA: number | null | undefined,
  runB: number | undefined,
): UseBatchImpactResult {
  const [state, setState] = useState<UseBatchImpactResult>({ summary: null, loading: true, error: false, blocked: false })

  useEffect(() => {
    if (runA !== undefined && runA !== null && runB !== undefined && runA === runB) {
      setState({ summary: null, loading: false, error: false, blocked: true })
      return
    }

    let cancelled = false
    setState({ summary: null, loading: true, error: false, blocked: false })
    const params = new URLSearchParams()
    if (runA !== undefined) params.set('run_a', runA === null ? 'start' : String(runA))
    if (runB !== undefined) params.set('run_b', String(runB))
    const query = params.toString()
    fetch(`${API_BASE}/api/batch-impact/summary${query ? `?${query}` : ''}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<BatchImpactSummary>
      })
      .then((summary) => {
        if (!cancelled) setState({ summary, loading: false, error: false, blocked: false })
      })
      .catch(() => {
        if (!cancelled) setState({ summary: null, loading: false, error: true, blocked: false })
      })
    return () => {
      cancelled = true
    }
  }, [runA, runB])

  return state
}

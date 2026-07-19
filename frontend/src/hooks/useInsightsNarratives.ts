import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseNarrativeResult {
  narrative: string | null
  generatedAt: string | null
  loading: boolean
  error: boolean
  generating: boolean
  generateError: string | null
  generate: () => void
}

interface NarrativeBody {
  narrative: string | null
  generated_at: string | null
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

// Shared by useInsightsSynthesis/useInsightsCoaching -- identical shape to
// useOpeningNarrative, minus the family/color path params (these two fetch
// on mount, unconditionally, instead of waiting on a selection).
function useNarrative(fetchPath: string, generatePath: string): UseNarrativeResult {
  const [narrative, setNarrative] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}${fetchPath}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<NarrativeBody>
      })
      .then((body) => {
        if (cancelled) return
        setNarrative(body.narrative)
        setGeneratedAt(body.generated_at)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setNarrative(null)
        setGeneratedAt(null)
        setLoading(false)
        setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [fetchPath])

  function generate() {
    setGenerating(true)
    setGenerateError(null)
    fetch(`${API_BASE}${generatePath}`, { method: 'POST' })
      .then(async (r) => {
        if (!r.ok) throw new Error(await errorDetail(r))
        return r.json() as Promise<{ narrative: string }>
      })
      .then((body) => {
        setNarrative(body.narrative)
        setGeneratedAt(new Date().toISOString())
        setGenerating(false)
      })
      .catch((err: Error) => {
        setGenerating(false)
        setGenerateError(err.message)
      })
  }

  return { narrative, generatedAt, loading, error, generating, generateError, generate }
}

export function useInsightsSynthesis(): UseNarrativeResult {
  return useNarrative('/api/insights/synthesis', '/api/insights/synthesis/generate')
}

export function useInsightsCoaching(): UseNarrativeResult {
  return useNarrative('/api/insights/coaching', '/api/insights/coaching/generate')
}

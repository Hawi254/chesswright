import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseOpponentNarrativeResult {
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

export function useOpponentNarrative(opponentName: string | null): UseOpponentNarrativeResult {
  const [narrative, setNarrative] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)

  useEffect(() => {
    setGenerateError(null)
    if (!opponentName) {
      setNarrative(null)
      setGeneratedAt(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(false)
    fetch(`${API_BASE}/api/matchups/opponent-narrative?opponent_name=${encodeURIComponent(opponentName)}`)
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
  }, [opponentName])

  function generate() {
    if (!opponentName) return
    setGenerating(true)
    setGenerateError(null)
    fetch(`${API_BASE}/api/matchups/opponent-narrative/generate?opponent_name=${encodeURIComponent(opponentName)}`, {
      method: 'POST',
    })
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

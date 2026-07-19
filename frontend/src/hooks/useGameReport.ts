import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseGameReportResult {
  reportText: string | null
  generatedAt: string | null
  loading: boolean
  generate: () => void
  generating: boolean
  error: string | null
  errorStatus: number | null
}

interface ReportBody {
  report_text: string | null
  generated_at: string | null
}

async function errorInfo(r: Response): Promise<{ message: string; status: number }> {
  const body = await r.json().catch(() => null)
  const message = (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
  return { message, status: r.status }
}

export function useGameReport(gameId: string | null): UseGameReportResult {
  const [reportText, setReportText] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorStatus, setErrorStatus] = useState<number | null>(null)

  useEffect(() => {
    setError(null)
    setErrorStatus(null)
    if (!gameId) {
      setReportText(null)
      setGeneratedAt(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    fetch(`${API_BASE}/api/games/${gameId}/report`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<ReportBody>
      })
      .then((body) => {
        if (cancelled) return
        setReportText(body.report_text)
        setGeneratedAt(body.generated_at)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setReportText(null)
        setGeneratedAt(null)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [gameId])

  function generate() {
    if (!gameId) return
    setGenerating(true)
    setError(null)
    setErrorStatus(null)
    fetch(`${API_BASE}/api/games/${gameId}/report/generate`, { method: 'POST' })
      .then(async (r) => {
        if (!r.ok) {
          const { message, status } = await errorInfo(r)
          const err = new Error(message) as Error & { status: number }
          err.status = status
          throw err
        }
        return r.json() as Promise<ReportBody>
      })
      .then((body) => {
        setReportText(body.report_text)
        setGeneratedAt(body.generated_at)
        setGenerating(false)
      })
      .catch((err: Error & { status?: number }) => {
        setGenerating(false)
        setError(err.message)
        setErrorStatus(err.status ?? null)
      })
  }

  return { reportText, generatedAt, loading, generate, generating, error, errorStatus }
}

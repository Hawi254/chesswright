import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseTournamentPrepReportResult {
  reportHtml: string | null
  generatedAt: string | null
  generate: () => void
  generating: boolean
  error: string | null
  errorStatus: number | null
}

interface ReportBody {
  report_html: string | null
  generated_at: string | null
}

async function errorInfo(r: Response): Promise<{ message: string; status: number }> {
  const body = await r.json().catch(() => null)
  const message = (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
  return { message, status: r.status }
}

export function useTournamentPrepReport(username: string): UseTournamentPrepReportResult {
  const [reportHtml, setReportHtml] = useState<string | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorStatus, setErrorStatus] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/opponent-prep/${encodeURIComponent(username)}/tournament-report`)
      .then((r) => (r.ok ? (r.json() as Promise<ReportBody>) : Promise.reject()))
      .then((body) => {
        if (cancelled) return
        setReportHtml(body.report_html)
        setGeneratedAt(body.generated_at)
      })
      .catch(() => {
        if (cancelled) return
        setReportHtml(null)
        setGeneratedAt(null)
      })
    return () => {
      cancelled = true
    }
  }, [username])

  function generate() {
    setGenerating(true)
    setError(null)
    setErrorStatus(null)
    fetch(`${API_BASE}/api/opponent-prep/${encodeURIComponent(username)}/tournament-report/generate`, {
      method: 'POST',
    })
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
        setReportHtml(body.report_html)
        setGeneratedAt(body.generated_at)
        setGenerating(false)
      })
      .catch((err: Error & { status?: number }) => {
        setGenerating(false)
        setError(err.message)
        setErrorStatus(err.status ?? null)
      })
  }

  return { reportHtml, generatedAt, generate, generating, error, errorStatus }
}

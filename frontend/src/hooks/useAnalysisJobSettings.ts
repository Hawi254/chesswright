import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface AnalysisJobSettings {
  depth: number
  multipv: number
  threads: number
  hashMb: number
  maxGames: number | null
  maxDuration: string | null
}

export interface UseAnalysisJobSettingsResult {
  settings: AnalysisJobSettings | null
  loading: boolean
  error: boolean
  saving: boolean
  saveError: string | null
  save: (next: AnalysisJobSettings) => Promise<void>
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

export function useAnalysisJobSettings(): UseAnalysisJobSettingsResult {
  const [settings, setSettings] = useState<AnalysisJobSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/analysis-jobs/settings`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<AnalysisJobSettings>
      })
      .then((body) => {
        if (cancelled) return
        setSettings(body)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function save(next: AnalysisJobSettings) {
    setSaving(true)
    setSaveError(null)
    try {
      const r = await fetch(`${API_BASE}/api/analysis-jobs/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          depth: next.depth,
          multipv: next.multipv,
          max_games: next.maxGames,
          max_duration: next.maxDuration,
          threads: next.threads,
          hash_mb: next.hashMb,
        }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setSettings(next)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save settings.')
    } finally {
      setSaving(false)
    }
  }

  return { settings, loading, error, saving, saveError, save }
}

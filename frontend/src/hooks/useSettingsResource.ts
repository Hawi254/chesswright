import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface UseSettingsResourceResult<T> {
  value: T | null
  loading: boolean
  error: boolean
  saving: boolean
  saveError: string | null
  save: (next: T) => Promise<void>
  resetting: boolean
  resetError: string | null
  reset: () => Promise<void>
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

export function useSettingsResource<T>(endpoint: string, resetEndpoint?: string): UseSettingsResourceResult<T> {
  const [value, setValue] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}${endpoint}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<T>
      })
      .then((body) => {
        if (cancelled) return
        setValue(body)
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
  }, [endpoint])

  async function save(next: T) {
    setSaving(true)
    setSaveError(null)
    try {
      const r = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setValue((await r.json()) as T)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save settings.')
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    if (!resetEndpoint) return
    setResetting(true)
    setResetError(null)
    try {
      const r = await fetch(`${API_BASE}${resetEndpoint}`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
      setValue((await r.json()) as T)
    } catch (err) {
      setResetError(err instanceof Error ? err.message : 'Failed to reset settings.')
    } finally {
      setResetting(false)
    }
  }

  return { value, loading, error, saving, saveError, save, resetting, resetError, reset }
}

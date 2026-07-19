import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface ApiKeyStatus {
  configured: boolean
  masked: string | null
  secureBackend: boolean
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

async function fetchStatus(): Promise<ApiKeyStatus> {
  const r = await fetch(`${API_BASE}/api/settings/api-key`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<ApiKeyStatus>
}

export function useApiKeySettings() {
  const [status, setStatus] = useState<ApiKeyStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [removing, setRemoving] = useState(false)
  const [removeError, setRemoveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchStatus()
      .then((body) => {
        if (cancelled) return
        setStatus(body)
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

  async function saveKey(key: string) {
    setSaving(true)
    setSaveError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/api-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setStatus(await fetchStatus())
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save API key.')
    } finally {
      setSaving(false)
    }
  }

  async function removeKey() {
    setRemoving(true)
    setRemoveError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/api-key`, { method: 'DELETE' })
      if (!r.ok) throw new Error(await errorDetail(r))
      setStatus(await fetchStatus())
    } catch (err) {
      setRemoveError(err instanceof Error ? err.message : 'Failed to remove API key.')
    } finally {
      setRemoving(false)
    }
  }

  return { status, loading, error, saving, saveError, saveKey, removing, removeError, removeKey }
}

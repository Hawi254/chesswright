import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

export function useEngineProfiles() {
  const [profiles, setProfiles] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/settings/engine-profiles`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ profiles: string[] }>
      })
      .then((body) => {
        if (cancelled) return
        setProfiles(body.profiles)
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

  async function saveProfile(name: string) {
    setSaving(true)
    setSaveError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine-profiles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setProfiles((await r.json()).profiles)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save profile.')
    } finally {
      setSaving(false)
    }
  }

  async function applyProfile(name: string) {
    setApplying(true)
    setApplyError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine-profiles/${encodeURIComponent(name)}/apply`, {
        method: 'POST',
      })
      if (!r.ok) throw new Error(await errorDetail(r))
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : 'Failed to apply profile.')
    } finally {
      setApplying(false)
    }
  }

  async function deleteProfile(name: string) {
    setDeleting(true)
    setDeleteError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine-profiles/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setProfiles((await r.json()).profiles)
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete profile.')
    } finally {
      setDeleting(false)
    }
  }

  return {
    profiles, loading, error,
    saving, saveError, saveProfile,
    applying, applyError, applyProfile,
    deleting, deleteError, deleteProfile,
  }
}

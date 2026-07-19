import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface ProLicenseDetail {
  available: boolean
  configured?: boolean
  masked?: string | null
  purchaseEmail?: string | null
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

async function fetchStatusAndLicense(): Promise<{ active: boolean; license: ProLicenseDetail }> {
  const statusRes = await fetch(`${API_BASE}/api/pro-status`)
  if (!statusRes.ok) throw new Error(`status ${statusRes.status}`)
  const { active } = (await statusRes.json()) as { active: boolean }

  const licenseRes = await fetch(`${API_BASE}/api/settings/pro-license`)
  if (!licenseRes.ok) throw new Error(`status ${licenseRes.status}`)
  const license = (await licenseRes.json()) as ProLicenseDetail

  return { active, license }
}

export function useProLicense() {
  const [active, setActive] = useState<boolean | null>(null)
  const [license, setLicense] = useState<ProLicenseDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [activating, setActivating] = useState(false)
  const [activateError, setActivateError] = useState<string | null>(null)
  const [activateMessage, setActivateMessage] = useState<string | null>(null)
  const [deactivating, setDeactivating] = useState(false)
  const [deactivateError, setDeactivateError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchStatusAndLicense()
      .then((body) => {
        if (cancelled) return
        setActive(body.active)
        setLicense(body.license)
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

  async function activate(key: string) {
    setActivating(true)
    setActivateError(null)
    setActivateMessage(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/pro/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      const body = (await r.json()) as { message: string }
      setActivateMessage(body.message)
      const refreshed = await fetchStatusAndLicense()
      setActive(refreshed.active)
      setLicense(refreshed.license)
    } catch (err) {
      setActivateError(err instanceof Error ? err.message : 'Activation failed.')
    } finally {
      setActivating(false)
    }
  }

  async function deactivate() {
    setDeactivating(true)
    setDeactivateError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/pro/deactivate`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
      const refreshed = await fetchStatusAndLicense()
      setActive(refreshed.active)
      setLicense(refreshed.license)
    } catch (err) {
      setDeactivateError(err instanceof Error ? err.message : 'Deactivation failed.')
    } finally {
      setDeactivating(false)
    }
  }

  return {
    active, license, loading, error,
    activating, activateError, activateMessage, activate,
    deactivating, deactivateError, deactivate,
  }
}

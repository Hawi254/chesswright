import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface PendingImport {
  pendingId: string
  suggestedUsername: string
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

export function useDbImport() {
  const [pending, setPending] = useState<PendingImport | null>(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)

  async function startImport(path: string) {
    setImporting(true)
    setImportError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/db-import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setPending((await r.json()) as PendingImport)
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setImporting(false)
    }
  }

  async function confirmImport(username: string) {
    if (!pending) return
    setConfirming(true)
    setConfirmError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/db-import/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pending_id: pending.pendingId, username }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setPending(null)
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : 'Failed to switch databases.')
    } finally {
      setConfirming(false)
    }
  }

  async function cancelImport() {
    if (!pending) return
    await fetch(`${API_BASE}/api/settings/db-import/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pending_id: pending.pendingId }),
    })
    setPending(null)
  }

  return { pending, importing, importError, startImport, confirming, confirmError, confirmImport, cancelImport }
}

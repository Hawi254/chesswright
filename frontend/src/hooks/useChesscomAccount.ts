import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

export function useChesscomAccount() {
  const [username, setUsername] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [pending, setPending] = useState(false)
  const [pendingError, setPendingError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/settings/chesscom`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ username: string | null }>
      })
      .then((body) => {
        if (cancelled) return
        setUsername(body.username)
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

  async function connect(newUsername: string) {
    setPending(true)
    setPendingError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/chesscom`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: newUsername }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      const body = (await r.json()) as { username: string }
      setUsername(body.username)
    } catch (err) {
      setPendingError(err instanceof Error ? err.message : 'Failed to connect.')
    } finally {
      setPending(false)
    }
  }

  async function disconnect() {
    setPending(true)
    setPendingError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/chesscom`, { method: 'DELETE' })
      if (!r.ok) throw new Error(await errorDetail(r))
      setUsername(null)
    } catch (err) {
      setPendingError(err instanceof Error ? err.message : 'Failed to disconnect.')
    } finally {
      setPending(false)
    }
  }

  async function syncNow() {
    setPending(true)
    setPendingError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/chesscom/sync`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
    } catch (err) {
      setPendingError(err instanceof Error ? err.message : 'Sync failed.')
    } finally {
      setPending(false)
    }
  }

  return { username, loading, error, pending, pendingError, connect, disconnect, syncNow }
}

import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface LiveEngineSettings {
  timeSec: number
  depth: number
  threads: number
  hashMb: number
  storeThreshold: number
  useLichessCloudEval: boolean
}

export interface EnginePayload {
  path: string | null
  detectedPath: string | null
  live: LiveEngineSettings
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return body && typeof body.detail === 'string' ? body.detail : `status ${r.status}`
}

export function useEngineSettings() {
  const [engine, setEngine] = useState<EnginePayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [settingPath, setSettingPath] = useState(false)
  const [pathError, setPathError] = useState<string | null>(null)
  const [redetecting, setRedetecting] = useState(false)
  const [redetectError, setRedetectError] = useState<string | null>(null)
  const [savingLive, setSavingLive] = useState(false)
  const [liveError, setLiveError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)

  async function refetch() {
    const r = await fetch(`${API_BASE}/api/settings/engine`)
    if (r.ok) setEngine((await r.json()) as EnginePayload)
  }

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/settings/engine`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<EnginePayload>
      })
      .then((body) => {
        if (cancelled) return
        setEngine(body)
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

  async function setPath(path: string) {
    setSettingPath(true)
    setPathError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine/path`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setEngine((await r.json()) as EnginePayload)
    } catch (err) {
      setPathError(err instanceof Error ? err.message : 'Failed to set engine path.')
    } finally {
      setSettingPath(false)
    }
  }

  async function redetect() {
    setRedetecting(true)
    setRedetectError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine/redetect`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
      setEngine((await r.json()) as EnginePayload)
    } catch (err) {
      setRedetectError(err instanceof Error ? err.message : 'No Stockfish installation was found.')
    } finally {
      setRedetecting(false)
    }
  }

  async function saveLive(live: LiveEngineSettings) {
    setSavingLive(true)
    setLiveError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine/live`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          time_sec: live.timeSec,
          depth: live.depth,
          threads: live.threads,
          hash_mb: live.hashMb,
          store_threshold: live.storeThreshold,
          use_lichess_cloud_eval: live.useLichessCloudEval,
        }),
      })
      if (!r.ok) throw new Error(await errorDetail(r))
      setEngine((await r.json()) as EnginePayload)
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : 'Failed to save live engine settings.')
    } finally {
      setSavingLive(false)
    }
  }

  async function reset() {
    setResetting(true)
    setResetError(null)
    try {
      const r = await fetch(`${API_BASE}/api/settings/engine/reset`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
      setEngine((await r.json()) as EnginePayload)
    } catch (err) {
      setResetError(err instanceof Error ? err.message : 'Failed to reset engine settings.')
    } finally {
      setResetting(false)
    }
  }

  return {
    engine, loading, error, refetch,
    settingPath, pathError, setPath,
    redetecting, redetectError, redetect,
    savingLive, liveError, saveLive,
    resetting, resetError, reset,
  }
}

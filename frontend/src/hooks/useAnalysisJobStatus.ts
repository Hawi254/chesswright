import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export type AnalysisJobStatusValue = 'idle' | 'starting' | 'running' | 'stopping' | 'error' | 'done'

export interface AnalysisJobRun {
  gamesDone: number
  runId?: number
  startedAt?: string
}

export interface AnalysisJobQueue {
  waiting: number
  analyzed: number
  failed: number
  awaitingAnnotation: number
}

export interface AnalysisJobTelemetry {
  reuseEvalsOn: boolean
  cacheHitRate: number | null
  estTimeSavedSec: number | null
  eta: number | null
}

// dataclasses.asdict(LockInfo) on the backend keeps LockInfo's own field
// name (started_at) verbatim rather than camelCasing it like the rest of
// this payload -- intentional, not an inconsistency to "fix" here.
export interface AnalysisJobLock {
  pid: number
  started_at: string
  alive: boolean
}

export interface AnalysisJobMaintenance {
  annotationPending: number
  backfillPending: number
  motifBackfillNeeded: boolean
}

export interface AnalysisJobStatus {
  status: AnalysisJobStatusValue
  runSeq: number
  completedRunId: number | null
  error: string | null
  run: AnalysisJobRun | null
  queue: AnalysisJobQueue
  telemetry: AnalysisJobTelemetry | null
  lock: AnalysisJobLock | null
  maintenance: AnalysisJobMaintenance
}

export interface UseAnalysisJobStatusResult {
  data: AnalysisJobStatus | null
  loading: boolean
  connectionLost: boolean
}

const POLL_INTERVAL_MS = 2000

// Python's datetime.isoformat() can emit up to 6 fractional-second
// digits (microseconds); the ECMAScript Date Time String grammar only
// guarantees 3-digit milliseconds, so extra digits are truncated before
// Date.parse rather than trusting every JS engine to accept 6.
function parseIsoTimestampMs(value: string): number {
  return new Date(value.replace(/(\.\d{3})\d*/, '$1')).getTime()
}

function withComputedEta(raw: AnalysisJobStatus): AnalysisJobStatus {
  if (!raw.telemetry || !raw.run || !raw.run.startedAt || raw.run.gamesDone <= 0) {
    return raw
  }
  const elapsedSec = (Date.now() - parseIsoTimestampMs(raw.run.startedAt)) / 1000
  const etaSec = raw.queue.waiting * (elapsedSec / raw.run.gamesDone)
  return { ...raw, telemetry: { ...raw.telemetry, eta: etaSec } }
}

export function useAnalysisJobStatus(): UseAnalysisJobStatusResult {
  const [data, setData] = useState<AnalysisJobStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [connectionLost, setConnectionLost] = useState(false)

  useEffect(() => {
    let cancelled = false

    function poll() {
      fetch(`${API_BASE}/api/analysis-jobs/status`)
        .then((r) => {
          if (!r.ok) throw new Error(`status ${r.status}`)
          return r.json() as Promise<AnalysisJobStatus>
        })
        .then((body) => {
          if (cancelled) return
          setData(withComputedEta(body))
          setLoading(false)
          setConnectionLost(false)
        })
        .catch(() => {
          if (cancelled) return
          setLoading(false)
          setConnectionLost(true)
        })
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return { data, loading, connectionLost }
}

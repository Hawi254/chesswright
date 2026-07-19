import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import { Button } from './ui/button'
import type { AnalysisJobStatus, AnalysisJobStatusValue } from '../hooks/useAnalysisJobStatus'

export interface ControlRailProps {
  data: AnalysisJobStatus | null
  onOpenSettings: () => void
}

const STATUS_LABEL: Record<AnalysisJobStatusValue, string> = {
  idle: 'Idle', starting: 'Starting…', running: 'Running',
  stopping: 'Stopping…', error: 'Error', done: 'Done',
}

const IN_PROGRESS: AnalysisJobStatusValue[] = ['starting', 'running', 'stopping']

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

export default function ControlRail({ data, onOpenSettings }: ControlRailProps) {
  // One shared in-flight flag, not three independent ones: data.status is
  // up to 2s stale by construction (poll interval), so without a shared
  // guard a user could double-click Start before the first POST's effect
  // is visible in the next poll tick.
  const [actionPending, setActionPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  async function postAction(path: string) {
    setActionPending(true)
    setActionError(null)
    try {
      const r = await fetch(`${API_BASE}${path}`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed.')
    } finally {
      setActionPending(false)
    }
  }

  const status = data?.status ?? 'idle'
  const running = IN_PROGRESS.includes(status)

  return (
    <div className="flex w-[260px] shrink-0 flex-col gap-4 border-r border-[var(--cw-line)] p-6">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${running ? 'bg-[var(--cw-cyan)]' : 'bg-[var(--cw-line)]'}`} />
        <span className="font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]">
          {STATUS_LABEL[status]}
        </span>
      </div>

      {running ? (
        <Button
          variant="destructive"
          disabled={actionPending || status === 'stopping'}
          onClick={() => postAction('/api/analysis-jobs/stop')}
        >
          Stop after current move
        </Button>
      ) : (
        <Button disabled={actionPending} onClick={() => postAction('/api/analysis-jobs/start')}>
          Start analysis batch
        </Button>
      )}
      {actionError && <p className="text-xs text-negative">{actionError}</p>}

      {data?.lock && !running && (
        <div className="rounded-md border border-[var(--cw-copper)]/40 bg-[var(--cw-panel)] p-3">
          {data.lock.alive ? (
            <p className="text-xs text-[var(--cw-copper)]">
              An analysis run is already in progress outside this app (pid {data.lock.pid}, started{' '}
              {data.lock.started_at}) -- most likely a `worker.py` run from a terminal. Stop that run
              first, then come back here.
            </p>
          ) : (
            <>
              <p className="text-xs text-[var(--cw-muted)]">
                A leftover lock from pid {data.lock.pid} was found, but that process is no longer
                running. Safe to clear.
              </p>
              <Button
                variant="outline" size="sm" className="mt-2"
                disabled={actionPending}
                onClick={() => postAction('/api/analysis-jobs/lock/clear')}
              >
                Clear stale lock
              </Button>
            </>
          )}
        </div>
      )}

      <div className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
        <div className="flex justify-between"><span>Waiting</span><span>{(data?.queue.waiting ?? 0).toLocaleString()}</span></div>
        <div className="flex justify-between"><span>Analyzed</span><span>{(data?.queue.analyzed ?? 0).toLocaleString()}</span></div>
        <div className="flex justify-between"><span>Failed</span><span>{(data?.queue.failed ?? 0).toLocaleString()}</span></div>
        <div className="flex justify-between"><span>Awaiting annotation</span><span>{(data?.queue.awaitingAnnotation ?? 0).toLocaleString()}</span></div>
      </div>

      <button
        type="button"
        onClick={onOpenSettings}
        className="text-left text-xs text-[var(--cw-muted)] hover:text-[var(--cw-text)]"
      >
        Engine and batch settings →
      </button>

      {/* No frozen-vs-source-checkout distinction here (unlike the
          Streamlit version's _throughput_caption()) -- the bundled status
          payload carries no such flag, and it isn't part of this design's
          stated parity requirements. */}
      <p className="mt-auto text-[10px] text-[var(--cw-muted)]">
        For max throughput, run a batch from the command line instead of this window.
      </p>
    </div>
  )
}

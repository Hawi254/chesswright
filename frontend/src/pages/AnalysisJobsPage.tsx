import { useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import { useAnalysisJobStatus } from '../hooks/useAnalysisJobStatus'
import ControlRail from '../components/ControlRail'
import JobSettingsDrawer from '../components/JobSettingsDrawer'
import RunTelemetry from '../components/RunTelemetry'
import MaintenanceCard from '../components/MaintenanceCard'
import BatchFinishedCard from '../components/BatchFinishedCard'

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

export default function AnalysisJobsPage() {
  const { data } = useAnalysisJobStatus()

  // Mounted on demand: JobSettingsDrawer's own hook fetches once on
  // mount, so it stays unmounted until the user opens it the first time,
  // then stays mounted (only its `open` prop toggles) so reopening it
  // doesn't refetch.
  const [settingsOpened, setSettingsOpened] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Per-run dismiss, mirroring the Streamlit version's run_seq-keyed
  // one-time-per-run dedupe (there via st.session_state, here via local
  // component state) -- a new run gets a new runSeq, so the card
  // reappears for it even if a prior run's card was dismissed.
  const [dismissedRunSeq, setDismissedRunSeq] = useState<number | null>(null)

  const [annotatePending, setAnnotatePending] = useState(false)
  const [annotateError, setAnnotateError] = useState<string | null>(null)
  const [backfillPending, setBackfillPending] = useState(false)
  const [backfillError, setBackfillError] = useState<string | null>(null)

  function openSettings() {
    setSettingsOpened(true)
    setDrawerOpen(true)
  }

  async function runAnnotation() {
    setAnnotatePending(true)
    setAnnotateError(null)
    try {
      const r = await fetch(`${API_BASE}/api/analysis-jobs/annotate`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
    } catch (err) {
      setAnnotateError(err instanceof Error ? err.message : 'Annotation pass failed.')
    } finally {
      setAnnotatePending(false)
    }
  }

  async function runBackfill() {
    setBackfillPending(true)
    setBackfillError(null)
    try {
      const r = await fetch(`${API_BASE}/api/analysis-jobs/backfill`, { method: 'POST' })
      if (!r.ok) throw new Error(await errorDetail(r))
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : 'Cache backfill failed.')
    } finally {
      setBackfillPending(false)
    }
  }

  const running = data?.status === 'running'
  const showBatchFinished =
    data != null && data.completedRunId != null && !running && data.runSeq !== dismissedRunSeq

  return (
    <div className="flex min-h-full" data-testid="analysis-jobs-page">
      <ControlRail data={data} onOpenSettings={openSettings} />

      <div className="flex-1 overflow-y-auto p-8">
        <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Analysis Jobs</h1>

        {showBatchFinished && data && (
          <div className="mt-4">
            <BatchFinishedCard
              runId={data.completedRunId as number}
              onDismiss={() => setDismissedRunSeq(data.runSeq)}
            />
          </div>
        )}

        {data?.telemetry && (
          <div className="mt-6">
            <RunTelemetry telemetry={data.telemetry} />
          </div>
        )}

        {!running && data && (data.maintenance.annotationPending > 0 || data.maintenance.motifBackfillNeeded) && (
          <div className="mt-6">
            <MaintenanceCard
              headline={
                data.maintenance.annotationPending > 0
                  ? `${data.maintenance.annotationPending.toLocaleString()} game(s) are analyzed but not yet annotated.`
                  : 'Some analyzed games are missing tactical motif data.'
              }
              buttonLabel="Run annotation pass now"
              onAction={runAnnotation}
              pending={annotatePending}
              error={annotateError}
            />
          </div>
        )}

        {!running && data && data.maintenance.backfillPending > 0 && (
          <div className="mt-6">
            <MaintenanceCard
              headline={`${data.maintenance.backfillPending.toLocaleString()} position group(s) haven't been backfilled into the eval-reuse cache yet.`}
              buttonLabel="Backfill eval-reuse cache now"
              onAction={runBackfill}
              pending={backfillPending}
              error={backfillError}
            />
          </div>
        )}
      </div>

      {settingsOpened && (
        <JobSettingsDrawer open={drawerOpen} onOpenChange={setDrawerOpen} readOnly={running ?? false} />
      )}
    </div>
  )
}

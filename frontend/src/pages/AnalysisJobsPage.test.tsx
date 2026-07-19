import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AnalysisJobsPage from './AnalysisJobsPage'

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, json: async () => body })
}

const RUNNING_STATUS = {
  status: 'running', runSeq: 3, completedRunId: null, error: null,
  run: { gamesDone: 4, runId: 9, startedAt: '2026-07-08T00:00:00+00:00' },
  queue: { waiting: 6, analyzed: 4, failed: 0, awaitingAnnotation: 0 },
  telemetry: { reuseEvalsOn: true, cacheHitRate: 0.4, estTimeSavedSec: 20, eta: 300 },
  lock: null,
  maintenance: { annotationPending: 5, backfillPending: 3, motifBackfillNeeded: false },
}

const IDLE_WITH_MAINTENANCE = {
  ...RUNNING_STATUS, status: 'idle', run: null, telemetry: null,
}

describe('AnalysisJobsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('hides maintenance cards while a batch is running', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(RUNNING_STATUS)))
    render(<AnalysisJobsPage />)

    await waitFor(() => expect(screen.getByText('Running')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Run annotation pass now' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Backfill eval-reuse cache now' })).not.toBeInTheDocument()
  })

  it('shows maintenance cards while idle with pending work', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(IDLE_WITH_MAINTENANCE)))
    render(<AnalysisJobsPage />)

    await waitFor(() => expect(
      screen.getByRole('button', { name: 'Run annotation pass now' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Backfill eval-reuse cache now' })).toBeInTheDocument()
  })

  it('shows RunTelemetry only when telemetry is present', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(RUNNING_STATUS)))
    render(<AnalysisJobsPage />)
    await waitFor(() => expect(screen.getByTestId('run-telemetry')).toBeInTheDocument())
  })

  it('does not mount the settings drawer until the settings row is opened', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(IDLE_WITH_MAINTENANCE)))
    render(<AnalysisJobsPage />)
    await waitFor(() => expect(screen.getByText('Idle')).toBeInTheDocument())
    expect(screen.queryByTestId('job-settings-drawer')).not.toBeInTheDocument()
  })
})

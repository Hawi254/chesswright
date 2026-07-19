import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ControlRail from './ControlRail'
import type { AnalysisJobStatus } from '../hooks/useAnalysisJobStatus'

function statusFixture(overrides: Partial<AnalysisJobStatus> = {}): AnalysisJobStatus {
  return {
    status: 'idle', runSeq: 0, completedRunId: null, error: null, run: null,
    queue: { waiting: 3, analyzed: 10, failed: 1, awaitingAnnotation: 2 },
    telemetry: null, lock: null,
    maintenance: { annotationPending: 2, backfillPending: 0, motifBackfillNeeded: false },
    ...overrides,
  }
}

describe('ControlRail', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it.each(['idle', 'starting', 'running', 'stopping', 'error', 'done'] as const)(
    'renders a status label for %s',
    (status) => {
      render(<ControlRail data={statusFixture({ status })} onOpenSettings={() => {}} />)
      expect(screen.getByText(/Idle|Starting…|Running|Stopping…|Error|Done/)).toBeInTheDocument()
    },
  )

  it('shows Start when idle and Stop when running', () => {
    const { rerender } = render(<ControlRail data={statusFixture({ status: 'idle' })} onOpenSettings={() => {}} />)
    expect(screen.getByRole('button', { name: 'Start analysis batch' })).toBeInTheDocument()

    rerender(<ControlRail data={statusFixture({ status: 'running' })} onOpenSettings={() => {}} />)
    expect(screen.getByRole('button', { name: 'Stop after current move' })).toBeInTheDocument()
  })

  it('posts to /start when Start is clicked', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ ok: true }) }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ControlRail data={statusFixture({ status: 'idle' })} onOpenSettings={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start analysis batch' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/analysis-jobs/start'),
      expect.objectContaining({ method: 'POST' }),
    ))
  })

  it('posts to /stop when Stop is clicked', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ ok: true }) }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ControlRail data={statusFixture({ status: 'running' })} onOpenSettings={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Stop after current move' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/analysis-jobs/stop'),
      expect.objectContaining({ method: 'POST' }),
    ))
  })

  it('disables all three action buttons while any action is in-flight', async () => {
    let resolveFetch: (v: unknown) => void = () => {}
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ControlRail
      data={statusFixture({ status: 'idle', lock: { pid: 1, started_at: 't0', alive: false } })}
      onOpenSettings={() => {}}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'Start analysis batch' }))

    expect(screen.getByRole('button', { name: 'Start analysis batch' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Clear stale lock' })).toBeDisabled()

    resolveFetch({ ok: true, json: async () => ({ ok: true }) })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Start analysis batch' })).not.toBeDisabled())
  })

  it('shows a live-lock warning without a clear button when the lock is alive', () => {
    render(<ControlRail
      data={statusFixture({ status: 'idle', lock: { pid: 999, started_at: 't0', alive: true } })}
      onOpenSettings={() => {}}
    />)
    expect(screen.getByText(/already in progress outside this app/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear stale lock' })).not.toBeInTheDocument()
  })

  it('shows a stale-lock notice with a clear button when the lock is not alive', () => {
    render(<ControlRail
      data={statusFixture({ status: 'idle', lock: { pid: 999, started_at: 't0', alive: false } })}
      onOpenSettings={() => {}}
    />)
    expect(screen.getByText(/no longer running/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear stale lock' })).toBeInTheDocument()
  })

  it('hides the lock warning while a batch is running', () => {
    render(<ControlRail
      data={statusFixture({ status: 'running', lock: { pid: 999, started_at: 't0', alive: true } })}
      onOpenSettings={() => {}}
    />)
    expect(screen.queryByText(/already in progress outside this app/)).not.toBeInTheDocument()
  })

  it('renders the queue counts', () => {
    render(<ControlRail data={statusFixture()} onOpenSettings={() => {}} />)
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  it('calls onOpenSettings when the settings row is clicked', () => {
    const onOpenSettings = vi.fn()
    render(<ControlRail data={statusFixture()} onOpenSettings={onOpenSettings} />)
    fireEvent.click(screen.getByText('Engine and batch settings →'))
    expect(onOpenSettings).toHaveBeenCalledTimes(1)
  })
})

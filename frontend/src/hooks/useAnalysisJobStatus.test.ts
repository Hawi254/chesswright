import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAnalysisJobStatus } from './useAnalysisJobStatus'

const IDLE_BODY = {
  status: 'idle', runSeq: 0, completedRunId: null, error: null, run: null,
  queue: { waiting: 0, analyzed: 0, failed: 0, awaitingAnnotation: 0 },
  telemetry: null, lock: null,
  maintenance: { annotationPending: 0, backfillPending: 0, motifBackfillNeeded: false },
}

describe('useAnalysisJobStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('fetches immediately on mount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => IDLE_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobStatus())
    await act(async () => {})

    expect(result.current.loading).toBe(false)
    expect(result.current.data?.status).toBe('idle')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/analysis-jobs/status'))
  })

  it('refetches every 2 seconds', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => IDLE_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useAnalysisJobStatus())
    await act(async () => {})
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('sets connectionLost after a failed poll tick, keeps last-known data', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => IDLE_BODY })
      .mockRejectedValueOnce(new Error('network down'))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobStatus())
    await act(async () => {})
    expect(result.current.connectionLost).toBe(false)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(result.current.connectionLost).toBe(true)
    expect(result.current.data?.status).toBe('idle')  // stale data retained, not cleared
  })

  it('recovers connectionLost on the next successful tick', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => IDLE_BODY })
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({ ok: true, json: async () => IDLE_BODY })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobStatus())
    await act(async () => { })
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(result.current.connectionLost).toBe(true)

    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(result.current.connectionLost).toBe(false)
  })

  it('stops polling on unmount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => IDLE_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = renderHook(() => useAnalysisJobStatus())
    await act(async () => {})
    unmount()

    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('computes ETA client-side once a run is in progress with games done', async () => {
    vi.setSystemTime(new Date('2026-07-08T00:10:00.000Z'))
    const runningBody = {
      ...IDLE_BODY,
      status: 'running',
      run: { gamesDone: 5, runId: 1, startedAt: '2026-07-08T00:00:00.000000+00:00' },
      queue: { waiting: 10, analyzed: 5, failed: 0, awaitingAnnotation: 0 },
      telemetry: { reuseEvalsOn: true, cacheHitRate: 0.5, estTimeSavedSec: 30, eta: null },
    }
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => runningBody }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobStatus())
    await act(async () => {})

    // elapsed = 600s over 5 games done => pace 120s/game; 10 waiting => eta 1200s
    expect(result.current.data?.telemetry?.eta).toBeCloseTo(1200, 0)
  })

  it('leaves eta null when no games are done yet this run', async () => {
    const runningBody = {
      ...IDLE_BODY,
      status: 'running',
      run: { gamesDone: 0, runId: 1, startedAt: '2026-07-08T00:00:00.000000+00:00' },
      telemetry: { reuseEvalsOn: true, cacheHitRate: null, estTimeSavedSec: null, eta: null },
    }
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => runningBody }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobStatus())
    await act(async () => {})

    expect(result.current.data?.telemetry?.eta).toBeNull()
  })
})

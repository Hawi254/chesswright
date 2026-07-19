import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useBatchImpact } from './useBatchImpact'
import type { BatchImpactSummary } from './useBatchImpact'

const SUMMARY: BatchImpactSummary = {
  runs: [], counter: { totalBatches: 0, totalGamesAnalyzed: 0 },
  range: { runA: null, runB: null }, pendingAnnotation: false, headline: null,
  records: [], trend: [], phase: [], endgame: [], motifs: [], newBlunders: [],
}

describe('useBatchImpact', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches with no query params when runA and runB are both undefined', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBatchImpact(undefined, undefined))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.summary).toEqual(SUMMARY)
    expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:8123/api/batch-impact/summary')
  })

  it('includes run_a and run_b when both are explicit numbers', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useBatchImpact(1, 2))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('run_a=1')
    expect(url).toContain('run_b=2')
  })

  it('sends run_a=start for the explicit "Start" sentinel (null, not undefined)', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useBatchImpact(null, 3))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toContain('run_a=start')
  })

  it('does not fetch and reports blocked when runA equals runB', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBatchImpact(2, 2))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.blocked).toBe(true)
    expect(result.current.summary).toBeNull()
  })

  it('sets error on a non-ok response', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBatchImpact(undefined, undefined))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.summary).toBeNull()
  })
})

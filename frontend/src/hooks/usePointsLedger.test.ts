import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePointsLedger } from './usePointsLedger'
import type { PointsSummary } from './usePointsLedger'

const SUMMARY: PointsSummary = {
  tc_options: [], n_games: 0, actual_pct: 0, leaked_points: 0, ceiling_pct: 0,
  buckets: [], monthly: [],
  conversion_breakdown: { adv_band: [], conv_phase: [], conv_clock: [] },
  causes: { reason: [], piece: [], mate: [] },
  costliest_games: [], analyzed_games: 0,
}

describe('usePointsLedger', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the unfiltered summary when timeControl is null', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePointsLedger(null))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.summary).toEqual(SUMMARY)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/points/summary')
    expect(fetchMock.mock.calls[0][0]).not.toContain('time_control')
  })

  it('includes time_control in the URL when set', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePointsLedger('bullet'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toContain('/api/points/summary?time_control=bullet')
  })

  it('sets error on a non-ok response', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePointsLedger(null))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.summary).toBeNull()
  })

  it('refetches when timeControl changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(({ tc }) => usePointsLedger(tc), { initialProps: { tc: null as string | null } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ tc: 'blitz' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('/api/points/summary?time_control=blitz')
  })
})

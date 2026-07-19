import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsClockTime } from './usePatternsClockTime'

const BODY = {
  blunder_rate_by_time_pressure: [{ bucket: 'critical (<5%)', n_moves: 10, acpl: 80, blunder_rate: 20 }],
  acpl_by_time_control: [{ time_control: 'blitz', n_games: 5, n_moves: 100, acpl: 40, blunder_rate: 5 }],
  thinking_time_blunder_correlation: [{ bucket: 'instant (<1s)', n_moves: 10, acpl: 60, blunder_rate: 15 }],
  instant_move_rate_by_phase: [{ bucket: 'opening (1-10)', n_moves: 20, n_instant: 4, instant_pct: 20 }],
  instant_move_accuracy: {
    rows: [{ bucket: 'forced-ish (≤3 legal replies)', n_moves: 5, acpl: 90, blunder_rate: 40 }],
    n_analyzed: 5,
    n_total_in_scope: 50,
  },
}

describe('usePatternsClockTime', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsClockTime())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/clock-time')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsClockTime())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

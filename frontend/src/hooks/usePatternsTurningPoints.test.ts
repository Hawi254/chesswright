import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsTurningPoints } from './usePatternsTurningPoints'

const BODY = {
  n_losses: 2,
  median_move: 14,
  most_common_phase: 'middlegame',
  by_move_bucket: [{ bucket: '6–10', n_losses: 1 }, { bucket: '21–25', n_losses: 1 }],
  by_phase: [{ phase: 'opening', n_losses: 1 }, { phase: 'middlegame', n_losses: 1 }],
  by_clock_bucket: [{ bucket: 'comfortable (30-60%)', n_losses: 1 }],
  n_no_clock_data: 1,
}

describe('usePatternsTurningPoints', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsTurningPoints())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/turning-points')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsTurningPoints())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

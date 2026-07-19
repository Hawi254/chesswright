import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useHeadlineStats } from './useHeadlineStats'

describe('useHeadlineStats', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches once on mount and reports stats', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({ total_games: 100, analyzed_games: 40, acpl: 32.1, blunder_rate: 5.2, win_pct: 55, n_analyzed_moves: 2000, implied_rating: 1500, rating_confidence: 'medium' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useHeadlineStats())
    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.stats?.analyzed_games).toBe(40)
    expect(result.current.error).toBe(false)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/overview/headline-stats'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports error on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))

    const { result } = renderHook(() => useHeadlineStats())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.stats).toBeNull()
  })
})

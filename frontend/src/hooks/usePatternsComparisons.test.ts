import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsComparisons } from './usePatternsComparisons'

const BODY = {
  favorite_underdog: {
    win: [{ bucket: 'underdog', n_games: 2, win_pct: 50 }],
    acpl: [{ bucket: 'underdog', n_games: 1, n_moves: 1, acpl: 10 }],
  },
  clock_pressure_by_rating_bucket: [
    { rating_bucket: 'underdog', time_bucket: 'critical (<5%)', n_moves: 1, acpl: 150, blunder_rate: 100 },
  ],
  openings_by_rating_bucket: [
    { rating_bucket: 'underdog', opening_family: 'Sicilian Defense', n_games: 5, win_pct: 100 },
  ],
  clock_pressure_by_outcome: [
    { outcome: 'win', time_bucket: 'plenty (60-100%)', n_moves: 1, acpl: 10, blunder_rate: 0 },
  ],
  clock_pressure_by_color: [
    { color: 'white', time_bucket: 'plenty (60-100%)', n_moves: 1, acpl: 10, blunder_rate: 0 },
  ],
  clock_pressure_by_opening: [
    { opening_family: "Queen's Gambit", time_bucket: 'critical (<5%)', n_moves: 1, acpl: 150, blunder_rate: 100 },
  ],
}

describe('usePatternsComparisons', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsComparisons())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/comparisons')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsComparisons())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMatchupsRatingForm } from './useMatchupsRatingForm'

const BODY = {
  win_rate_by_rating_diff: [{ band: -100, n: 5, win_pct: 40.0 }],
  color_performance_by_rating: [{ rating_bucket: 'even', black: 45.0, white: 50.0 }],
  giant_killing_counts: { n_upsets: 1, n_underdog_games: 3, n_collapses: 0, n_favorite_games: 2 },
  collapse_causes: { reason: [], piece: [], mate: [] },
  giant_killing_rate_trend: [],
  comeback_collapse: { n_comebacks: 1, n_collapses: 0, comeback_game_ids: ['g1'], collapse_game_ids: [] },
}

describe('useMatchupsRatingForm', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useMatchupsRatingForm())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/matchups/rating-form')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useMatchupsRatingForm())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

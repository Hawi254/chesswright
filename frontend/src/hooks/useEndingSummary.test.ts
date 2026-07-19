import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEndingSummary } from './useEndingSummary'

const SUMMARY = {
  hero: { total_games: 10, decisive_pct: 70.0, draw_pct: 30.0, resignation_explained_pct: 50.0, flagged_while_ahead_pct: 20.0 },
  endgame_material: [{ endgame_type: 'Queen', n_games: 5, win_pct: 60, draw_pct: 20, loss_pct: 20, acpl: 30.0, blunder_rate: 5.0 }],
  resignation_trend: [],
  time_forfeit_trend: [],
}

describe('useEndingSummary', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingSummary())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.summary).toEqual(SUMMARY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sets error on a non-ok response', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingSummary())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.summary).toBeNull()
  })
})

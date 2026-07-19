import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsGameContext } from './usePatternsGameContext'

const BODY = {
  phase_accuracy: [
    { phase: 'opening', n_games: 1, n_moves: 1, acpl: 10, blunder_rate: 0 },
    { phase: 'middlegame', n_games: 1, n_moves: 1, acpl: 200, blunder_rate: 100 },
  ],
  day_hour_heatmap: {
    cells: [{ day: 'Mon', hour_local: 12, win_pct: 50, rating_diff_display: '+25' }],
    utc_offset_hours: 0,
  },
}

describe('usePatternsGameContext', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsGameContext())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/game-context')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsGameContext())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

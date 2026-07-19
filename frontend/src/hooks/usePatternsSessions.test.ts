import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsSessions } from './usePatternsSessions'

const BODY = {
  session_rollup: [
    { session_start: '2026-01-01T10:00:00', session_end: '2026-01-01T10:05:00', n_games: 2,
      win_pct: 50, draw_pct: 0, loss_pct: 50, acpl: 10, n_analyzed: 1 },
  ],
  prior_outcome: [
    { bucket: 'first_game_of_session', n_games: 1, n_moves: 1, acpl: 10, blunder_rate: 0 },
  ],
  session_position: [
    { position: 'game #1', n_games: 1, n_moves: 1, acpl: 10, blunder_rate: 0 },
  ],
  event_type: [
    { category: 'Casual', n_games: 2, win_pct: 50, draw_pct: 0, loss_pct: 50, acpl: 10, n_analyzed: 1 },
  ],
  event_name_breakdown: [
    { event: 'Weekly Rapid Arena', n_games: 5, win_pct: 100, draw_pct: 0, loss_pct: 0, acpl: 20, n_analyzed: 5 },
  ],
}

describe('usePatternsSessions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsSessions())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/sessions')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsSessions())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningPositionTimeline } from './useOpeningPositionTimeline'

const RESPONSE = {
  summary: { split_year: 2025, before_san: 'Nc3', before_n: 5, before_total: 5, before_share: 100,
    before_win_pct: 60, before_cpl: 10, after_san: 'Nf3', after_n: 6, after_total: 6, after_share: 100,
    after_win_pct: 66.7, after_cpl: 8 },
  rows: [{ san: 'Nc3', year: 2024, is_player_move: true, n_games: 5, n_wins: 3, n_draws: 1, n_losses: 1, cpl_sum: 50, cpl_n: 5 }],
}

describe('useOpeningPositionTimeline', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when fen is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningPositionTimeline(null, 'w'))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.summary).toBeNull()
    expect(result.current.rows).toEqual([])
  })

  it('fetches timeline with fen/color query params', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => RESPONSE }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningPositionTimeline('fen1', 'w'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.summary).toEqual(RESPONSE.summary)
    expect(result.current.rows).toEqual(RESPONSE.rows)
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('fen=fen1')
    expect(url).toContain('color=w')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useOpeningPositionTimeline('fen1', 'w'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })
})

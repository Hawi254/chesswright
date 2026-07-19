import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useNemesisOpponents } from './useNemesisOpponents'

function row(overrides = {}) {
  return {
    opponent_name: 'Rival', n: 10, wins: 3, draws: 2, losses: 5, all_lichess: true, n_rated: 10,
    score_pct: 40.0, expected_score_pct: 50.0, surprise_pct: -10.0, confidence_tier: 'medium',
    ...overrides,
  }
}

describe('useNemesisOpponents', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches with the given min_games on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => [row()] }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useNemesisOpponents(5))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.rows).toEqual([row()])
    expect(fetchMock.mock.calls[0][0]).toContain('min_games=5')
  })

  it('refetches when minGames changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => [] }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(({ minGames }) => useNemesisOpponents(minGames), {
      initialProps: { minGames: 5 },
    })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ minGames: 10 })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('min_games=10')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useNemesisOpponents(5))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.rows).toBeNull()
  })
})

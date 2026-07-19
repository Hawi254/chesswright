import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useGameExplorer } from './useGameExplorer'

const SAMPLE_GAMES = [
  { game_id: 'abc123', utc_date: '2026-01-01', opponent_name: 'Foe', opponent_rating: 1500,
    player_color: 'white' as const, outcome_for_player: 'win' as const,
    time_control_category: 'blitz', opening_family: 'Sicilian Defense', rating_diff: 20,
    site: 'https://lichess.org/abc123', analysis_status: 'done', badge_count: 1,
    drama_score: 105, lichess_url: 'https://lichess.org/abc123', platform: 'Lichess' as const,
    is_comeback: true, is_giant_killing: false, is_brilliant_find: false,
    is_blunder_fest: false, is_nail_biter: false },
]

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useGameExplorer', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts loading, then populates games on success', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_GAMES))
    const { result } = renderHook(() => useGameExplorer())
    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(false)
    expect(result.current.games).toEqual(SAMPLE_GAMES)
  })

  it('reports an error state on a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useGameExplorer())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.games).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useGameExplorer())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })
})

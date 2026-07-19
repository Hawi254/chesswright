import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpponentProfile } from './useOpponentProfile'

const PROFILE = {
  n_games: 3,
  openings: [{ opening_family: 'Sicilian Defense', n_games: 2, win_pct: 50.0, acpl: 30.0 }],
  position: [{ bucket: 'open', n_games: 2, win_pct: 50.0 }],
  castling: [{ castling_config: 'same_side', n_games: 2, win_pct: 50.0 }],
  action_side: [{ action_side: 'kingside', n_games: 2, win_pct: 50.0 }],
  clock: [{ bucket: 'normal', n_moves: 20, acpl: 25.0, blunder_rate: 5.0 }],
}

describe('useOpponentProfile', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when opponentName is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpponentProfile(null))
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches and URL-encodes the opponent name once set', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => PROFILE }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpponentProfile('J. Rival'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.profile).toEqual(PROFILE)
    expect(fetchMock.mock.calls[0][0]).toContain(encodeURIComponent('J. Rival'))
  })
})

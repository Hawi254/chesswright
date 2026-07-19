import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCareerHighlight } from './useCareerHighlight'

const SAMPLE_GAMES = [
  {
    game_id: 'abc123',
    opponent_name: 'TestOpponent',
    utc_date: '2026-01-01',
    outcome_for_player: 'win' as const,
    is_comeback: true,
    is_giant_killing: false,
    is_brilliant_find: false,
    is_blunder_fest: false,
    is_nail_biter: true,
  },
]

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useCareerHighlight', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_GAMES))
    const { result } = renderHook(() => useCareerHighlight())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('populates the games when the request succeeds', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_GAMES))
    const { result } = renderHook(() => useCareerHighlight())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.games).toEqual(SAMPLE_GAMES)
  })

  it('treats an empty array as a valid success state, not an error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess([]))
    const { result } = renderHook(() => useCareerHighlight())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.games).toEqual([])
  })

  it('reports an error state if the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useCareerHighlight())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.games).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useCareerHighlight())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})

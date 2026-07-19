import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSavedVariations } from './useSavedVariations'

const VARIATION = {
  id: 'v1', game_id: 'game1', branch_ply: 2,
  branch_fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
  moves: ['g8f6'], title: null, created_at: '2026-07-14T00:00:00', updated_at: '2026-07-14T00:00:00',
}

describe('useSavedVariations', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches on mount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => [VARIATION] }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSavedVariations('game1'))

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.variations).toEqual([VARIATION])
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/games/game1/variations'))
  })

  it('returns an empty list and does not fetch when gameId is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSavedVariations(null))

    expect(result.current.variations).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sets an empty list on fetch failure rather than throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))

    const { result } = renderHook(() => useSavedVariations('game1'))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.variations).toEqual([])
  })

  it('refetch() re-fetches the list', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [VARIATION] })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSavedVariations('game1'))
    await waitFor(() => expect(result.current.variations).toEqual([VARIATION]))

    act(() => {
      result.current.refetch()
    })

    await waitFor(() => expect(result.current.variations).toEqual([]))
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

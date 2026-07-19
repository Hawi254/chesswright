import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningTreeMoves } from './useOpeningTreeMoves'

const MOVES = [{ san: 'e4', is_player_move: true, n_games: 10, n_wins: 6, n_draws: 2, n_losses: 2,
  win_pct: 60, draw_pct: 20, loss_pct: 20, avg_cpl: 15 }]

describe('useOpeningTreeMoves', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches moves with fen/ply/color/min_games query params', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => MOVES }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningTreeMoves('fen1', 1, 'w', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.moves).toEqual(MOVES)
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('/api/opening-tree/moves')
    expect(url).toContain('fen=fen1')
    expect(url).toContain('ply=1')
    expect(url).toContain('color=w')
    expect(url).toContain('min_games=3')
  })

  it('does not fetch when fen is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningTreeMoves(null, 1, 'w', 3))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.moves).toEqual([])
    expect(result.current.loading).toBe(false)
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useOpeningTreeMoves('fen1', 1, 'w', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.moves).toEqual([])
  })

  it('refetches when fen changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => MOVES }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(({ fen }) => useOpeningTreeMoves(fen, 1, 'w', 3), { initialProps: { fen: 'fen1' } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ fen: 'fen2' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})

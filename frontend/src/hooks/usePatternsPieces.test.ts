import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsPieces } from './usePatternsPieces'

const BODY = {
  piece_movement: [{ piece: 'Q', piece_name: 'queen', n_moves: 10, acpl: 40, blunder_rate: 10 }],
  piece_by_view: [{ piece: 'Q', piece_name: 'queen', phase: 'opening', n_moves: 5, blunder_rate: 5 }],
  bishop_square_color: [{ square_color: 'dark square', n_moves: 5, acpl: 30, blunder_rate: 5 }],
  rook_king_backrank: [{ piece: 'R', piece_name: 'rook', location: 'back rank', n_moves: 5, acpl: 20, blunder_rate: 5 }],
  square_heatmap: { cells: [{ file: 'e', rank: 4, blunder_rate: 20, n_moves: 25 }], n_analyzed: 25, n_total_in_scope: 25 },
  motif_backfill_needed: true,
  castling: {
    win: [{ status: 'castled', n_games: 1, win_pct: 100 }],
    acpl: [{ status: 'castled', n_games: 1, n_moves: 40, acpl: 15 }],
  },
}

describe('usePatternsPieces', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches with the given viewBy on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsPieces('phase'))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/pieces?view_by=phase')
  })

  it('refetches with the new view_by query param when viewBy changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result, rerender } = renderHook(({ viewBy }) => usePatternsPieces(viewBy), {
      initialProps: { viewBy: 'phase' as 'phase' | 'sharpness' },
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    rerender({ viewBy: 'sharpness' })
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][0]).toContain('/api/patterns/pieces?view_by=sharpness')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsPieces('phase'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

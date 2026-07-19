import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsPositions } from './usePatternsPositions'

const BODY = {
  sharpness: [{ bucket: 'flat (<5cp gap)', n_moves: 20, acpl: 5, blunder_rate: 1 }],
  material_structure: {
    rows: [{ label: 'Queen', n_games: 1, win_pct: 100, draw_pct: 0, loss_pct: 0,
              acpl: 10, n_analyzed: 1 }],
    label_header: 'Category',
    n_unanalyzed: 0,
  },
  bishop_endings: [],
  position_character: {
    bucket_win: [], bucket_acpl: [], symmetric_win: [], symmetric_acpl: [],
    central_tension_pct: null, n_classified: 0, n_total_games: 0,
  },
  game_side: { castling_win: [], castling_acpl: [], action_win: [], action_acpl: [] },
}

describe('usePatternsPositions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount with both query params', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsPositions('endgame', false))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/positions')
    expect(fetchMock.mock.calls[0][0]).toContain('structure_type=endgame')
    expect(fetchMock.mock.calls[0][0]).toContain('grouped=false')
  })

  it('refetches when structureType changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(
      ({ structureType, grouped }) => usePatternsPositions(structureType, grouped),
      { initialProps: { structureType: 'endgame' as const, grouped: false } },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ structureType: 'middlegame' as const, grouped: false })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('structure_type=middlegame')
  })

  it('refetches when grouped changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(
      ({ structureType, grouped }) => usePatternsPositions(structureType, grouped),
      { initialProps: { structureType: 'endgame' as const, grouped: false } },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ structureType: 'endgame' as const, grouped: true })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('grouped=true')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsPositions('endgame', false))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.data).toBeNull()
  })
})

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useGameDetail } from './useGameDetail'

const SAMPLE_BODY = {
  header: {
    game_id: 'abc123', utc_date: '2026-01-01', opponent_name: 'Foe', opponent_rating: 1500,
    player_rating: 1520, player_color: 'white' as const, outcome_for_player: 'win' as const,
    time_control_category: 'blitz', opening_family: "King's Pawn", rating_diff: 20,
    game_end_type: 'checkmate', analysis_status: 'done', last_analyzed_ply: 2,
    site: 'https://lichess.org/abc123', lichess_url: 'https://lichess.org/abc123',
    is_comeback: false, is_giant_killing: false, is_brilliant_find: false,
    is_blunder_fest: false, is_nail_biter: false,
  },
  moves: [
    { ply: 1, san: 'e4', is_player_move: 1, classification: 'good', cpl: 0, sharpness: 0.1,
      is_brilliant_candidate: false, is_puzzle_trigger: false,
      fen_before: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      fen_after: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      win_prob_before: 0.5, win_prob_after: 0.55, motif: null },
  ],
  win_prob: [{ ply: 1, player_win_prob: 0.55 }],
}

function mockFetchSuccess(body: unknown, status = 200) {
  // Typed with an explicit (unused) url param -- without it, vi.fn()
  // infers a zero-arg tuple from the implementation signature, and the
  // re-fetch test's `fetchMock.mock.calls[1][0]` fails to typecheck
  // (found live: a real TS2493 error, not just a lint nit).
  return vi.fn((_url: string) => Promise.resolve({ ok: status < 400, status, json: async () => body }))
}

describe('useGameDetail', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does not fetch when gameId is null', () => {
    const fetchMock = mockFetchSuccess(SAMPLE_BODY)
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useGameDetail(null))
    expect(result.current.loading).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('populates header/moves/winProb on success', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_BODY))
    const { result } = renderHook(() => useGameDetail('abc123'))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(false)
    expect(result.current.notFound).toBe(false)
    expect(result.current.header).toEqual(SAMPLE_BODY.header)
    expect(result.current.moves).toEqual(SAMPLE_BODY.moves)
    expect(result.current.winProb).toEqual(SAMPLE_BODY.win_prob)
  })

  it('reports notFound on a 404 without setting error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(null, 404))
    const { result } = renderHook(() => useGameDetail('does-not-exist'))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.notFound).toBe(true)
    expect(result.current.error).toBe(false)
    expect(result.current.header).toBeNull()
  })

  it('reports an error state on a non-404 failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useGameDetail('abc123'))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.notFound).toBe(false)
  })

  it('re-fetches when gameId changes', async () => {
    const fetchMock = mockFetchSuccess(SAMPLE_BODY)
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(({ id }) => useGameDetail(id), { initialProps: { id: 'abc123' } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    rerender({ id: 'def456' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('def456')
  })
})

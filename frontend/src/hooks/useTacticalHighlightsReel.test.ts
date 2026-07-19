import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTacticalHighlightsReel } from './useTacticalHighlightsReel'

const SAMPLE_MOMENT = {
  game_id: 'g1', category: 'brilliant', move_number: 5, san: 'Rxf7',
  magnitude: 500, magnitude_label: 'Rook sacrifice', strength: 0.56,
  caption: 'Sacrificed a rook on move 5 — it worked.',
  opponent_name: 'Rival', utc_date: '2026-01-01', outcome_for_player: 'win',
  player_color: 'white', fen: 'startpos', lastmove_from: 'f7', lastmove_to: 'f3',
}

const SAMPLE_BODY = {
  moments: [SAMPLE_MOMENT],
  counts: { brilliant: 1, puzzle_conversion: 0, best_move_streak: 0, blown_mate: 0, great_escape: 0 },
}

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useTacticalHighlightsReel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading, then resolves with moments and counts', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_BODY))
    const { result } = renderHook(() => useTacticalHighlightsReel())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(false)
    expect(result.current.moments).toEqual([SAMPLE_MOMENT])
    expect(result.current.counts).toEqual(SAMPLE_BODY.counts)
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useTacticalHighlightsReel())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.moments).toBeNull()
    expect(result.current.counts).toBeNull()
  })
})

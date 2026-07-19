import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useVariation } from './useVariation'
import type { SavedVariation } from './useSavedVariations'

const BRANCH_FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
const FEN_AFTER_NF6 = 'rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2'
const FEN_AFTER_NC3 = 'rnbqkb1r/pppppppp/5n2/8/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq - 2 2'

function fetchMockReturning(byMethod: Record<string, unknown>) {
  return vi.fn((_url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    return Promise.resolve({ ok: true, json: async () => byMethod[method] })
  })
}

describe('useVariation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts inactive', () => {
    vi.stubGlobal('fetch', vi.fn())
    const { result } = renderHook(() => useVariation('game1'))
    expect(result.current.active).toBe(false)
    expect(result.current.currentFen).toBeNull()
    expect(result.current.moves).toEqual([])
  })

  it('applyMove from inactive enters variation mode and POSTs to create it', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' } })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useVariation('game1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })

    expect(result.current.active).toBe(true)
    expect(result.current.branchPly).toBe(2)
    expect(result.current.moves).toEqual(['g8f6'])
    expect(result.current.currentFen).toBe(FEN_AFTER_NF6)
    expect(result.current.step).toBe(1)

    await waitFor(() => expect(result.current.variationId).toBe('v1'))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/games/game1/variations'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ branch_ply: 2, branch_fen: BRANCH_FEN, moves: ['g8f6'] }),
      }),
    )
  })

  it('applyMove while active appends the move and PUTs the full list', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' }, PUT: { ok: true } })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useVariation('game1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'b1c3', fen: FEN_AFTER_NC3, san: 'Nc3' })
    })

    expect(result.current.moves).toEqual(['g8f6', 'b1c3'])
    expect(result.current.step).toBe(2)
    expect(result.current.currentFen).toBe(FEN_AFTER_NC3)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/variations/v1'),
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ moves: ['g8f6', 'b1c3'] }) }),
    )
  })

  it('truncates moves after the current step before appending a move played from an earlier step', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' }, PUT: { ok: true } })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useVariation('game1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))
    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'b1c3', fen: FEN_AFTER_NC3, san: 'Nc3' })
    })
    act(() => {
      result.current.stepTo(1)
    })

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'd2d4', fen: 'ALT_FEN', san: 'd4' })
    })

    expect(result.current.moves).toEqual(['g8f6', 'd2d4'])
    expect(result.current.step).toBe(2)
  })

  it('stepTo clamps within bounds and makes no network call', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' } })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useVariation('game1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))
    const callsAfterCreate = fetchMock.mock.calls.length

    act(() => {
      result.current.stepTo(-5)
    })
    expect(result.current.step).toBe(0)
    expect(result.current.currentFen).toBe(BRANCH_FEN)

    act(() => {
      result.current.stepTo(999)
    })
    expect(result.current.step).toBe(1)
    expect(fetchMock.mock.calls.length).toBe(callsAfterCreate)
  })

  it('exit clears state without deleting the variation', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' } })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useVariation('game1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))
    const callsBeforeExit = fetchMock.mock.calls.length

    act(() => {
      result.current.exit()
    })

    expect(result.current.active).toBe(false)
    expect(result.current.moves).toEqual([])
    expect(fetchMock.mock.calls.length).toBe(callsBeforeExit)
  })

  it('discard DELETEs the variation and clears state', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' }, DELETE: { ok: true } })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useVariation('game1'))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))

    act(() => {
      result.current.discard()
    })

    expect(result.current.active).toBe(false)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/variations/v1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('load() replays a saved variation onto the branch FEN and jumps to the end', () => {
    vi.stubGlobal('fetch', vi.fn())
    const { result } = renderHook(() => useVariation('game1'))

    const saved: SavedVariation = {
      id: 'v9', game_id: 'game1', branch_ply: 2, branch_fen: BRANCH_FEN,
      moves: ['g8f6', 'b1c3'], title: null,
      created_at: '2026-07-14T00:00:00', updated_at: '2026-07-14T00:00:00',
    }

    act(() => {
      result.current.load(saved)
    })

    expect(result.current.active).toBe(true)
    expect(result.current.variationId).toBe('v9')
    expect(result.current.branchPly).toBe(2)
    expect(result.current.moves).toEqual(['g8f6', 'b1c3'])
    expect(result.current.sans).toEqual(['Nf6', 'Nc3'])
    expect(result.current.step).toBe(2)
    expect(result.current.currentFen).toBe(FEN_AFTER_NC3)
  })

  it('load() stops replay at the last legal move rather than throwing', () => {
    vi.stubGlobal('fetch', vi.fn())
    const { result } = renderHook(() => useVariation('game1'))

    const saved: SavedVariation = {
      id: 'v9', game_id: 'game1', branch_ply: 2, branch_fen: BRANCH_FEN,
      moves: ['g8f6', 'e2e4'], title: null,
      created_at: '2026-07-14T00:00:00', updated_at: '2026-07-14T00:00:00',
    }

    act(() => {
      result.current.load(saved)
    })

    expect(result.current.moves).toEqual(['g8f6'])
    expect(result.current.sans).toEqual(['Nf6'])
    expect(result.current.step).toBe(1)
    expect(result.current.currentFen).toBe(FEN_AFTER_NF6)
  })

  it('calls onMutated after a variation is created', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' } })
    vi.stubGlobal('fetch', fetchMock)
    const onMutated = vi.fn()
    const { result } = renderHook(() => useVariation('game1', onMutated))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))

    expect(onMutated).toHaveBeenCalled()
  })

  it('calls onMutated when discard() is called', async () => {
    const fetchMock = fetchMockReturning({ POST: { id: 'v1' }, DELETE: { ok: true } })
    vi.stubGlobal('fetch', fetchMock)
    const onMutated = vi.fn()
    const { result } = renderHook(() => useVariation('game1', onMutated))

    act(() => {
      result.current.applyMove(2, BRANCH_FEN, { uci: 'g8f6', fen: FEN_AFTER_NF6, san: 'Nf6' })
    })
    await waitFor(() => expect(result.current.variationId).toBe('v1'))
    onMutated.mockClear()

    act(() => {
      result.current.discard()
    })

    expect(onMutated).toHaveBeenCalled()
  })
})

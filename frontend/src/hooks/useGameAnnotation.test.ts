import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useGameAnnotation } from './useGameAnnotation'

const ANNOTATION = {
  id: 'ann1', move_index: 4, glyph: '!!', comment: 'Brilliant',
  ai_comment: null, ai_model: null, generated_at: null,
  variation_id: null, game_id: 'g1',
}

describe('useGameAnnotation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches on mount for a given gameId+ply', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ANNOTATION }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameAnnotation('g1', 4, 'FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.annotation).toEqual(ANNOTATION)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/games/g1/annotations/4'))
  })

  it('skips fetching when ply is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameAnnotation('g1', null, null))
    expect(result.current.annotation).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refetches when ply changes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ANNOTATION })
      .mockResolvedValueOnce({ ok: true, json: async () => null })
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ ply }) => useGameAnnotation('g1', ply, 'FEN'),
      { initialProps: { ply: 4 } },
    )
    await waitFor(() => expect(result.current.annotation).toEqual(ANNOTATION))

    rerender({ ply: 6 })
    await waitFor(() => expect(result.current.annotation).toBeNull())
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining('/api/games/g1/annotations/6'))
  })

  it('save() PUTs and optimistically merges the response', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => null })
      .mockResolvedValueOnce({ ok: true, json: async () => ANNOTATION })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameAnnotation('g1', 4, 'FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.save('!!', 'Brilliant')
    })
    await waitFor(() => expect(result.current.annotation).toEqual(ANNOTATION))
  })

  it('askClaude() surfaces the server detail message as aiError on 502', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => null })
      .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({ detail: 'Claude API call failed: timeout' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameAnnotation('g1', 4, 'FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.askClaude(null, null, null)
    })
    await waitFor(() => expect(result.current.aiError).toBe('Claude API call failed: timeout'))
  })
})

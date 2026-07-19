import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useVariationAnnotation } from './useVariationAnnotation'

const ANNOTATION = {
  id: 'ann1', move_index: 1, glyph: '!', comment: 'Good move',
  ai_comment: null, ai_model: null, generated_at: null,
  variation_id: 'v1', game_id: null,
}

describe('useVariationAnnotation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches on mount for a given variationId+step', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ANNOTATION }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVariationAnnotation('v1', 1, 'FEN'))
    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.annotation).toEqual(ANNOTATION)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/variations/v1/annotations/1'))
  })

  it('skips fetching and reports no annotation when variationId is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVariationAnnotation(null, 0, null))
    expect(result.current.annotation).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refetches when step changes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ANNOTATION })
      .mockResolvedValueOnce({ ok: true, json: async () => null })
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ step }) => useVariationAnnotation('v1', step, 'FEN'),
      { initialProps: { step: 1 } },
    )
    await waitFor(() => expect(result.current.annotation).toEqual(ANNOTATION))

    rerender({ step: 2 })
    await waitFor(() => expect(result.current.annotation).toBeNull())
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining('/api/variations/v1/annotations/2'))
  })

  it('save() PUTs and optimistically merges the response', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => null })
      .mockResolvedValueOnce({ ok: true, json: async () => ANNOTATION })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVariationAnnotation('v1', 1, 'FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.save('!', 'Good move')
    })
    await waitFor(() => expect(result.current.annotation).toEqual(ANNOTATION))
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/variations/v1/annotations/1'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ glyph: '!', comment: 'Good move' }),
      }),
    )
  })

  it('save() sets saveError on failure, leaves annotation unchanged', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => null })
      .mockResolvedValueOnce({ ok: false, status: 500 })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVariationAnnotation('v1', 1, 'FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.save('!', null)
    })
    await waitFor(() => expect(result.current.saveError).not.toBeNull())
    expect(result.current.annotation).toBeNull()
  })

  it('askClaude() POSTs with the given fen/evalCp/bestMoveSan and optimistically merges', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => null })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...ANNOTATION, ai_comment: 'Nice.' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVariationAnnotation('v1', 1, 'THE_FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.askClaude(40, 'Nf6', 'my note')
    })
    expect(result.current.aiLoading).toBe(true)
    await waitFor(() => expect(result.current.aiLoading).toBe(false))
    expect(result.current.annotation?.ai_comment).toBe('Nice.')
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/variations/v1/annotations/1/ai-comment'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ fen: 'THE_FEN', eval_cp: 40, best_move_san: 'Nf6', user_comment: 'my note' }),
      }),
    )
  })

  it('askClaude() surfaces the server detail message as aiError on 503', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => null })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'No Anthropic API key configured.' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVariationAnnotation('v1', 1, 'FEN'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.askClaude(null, null, null)
    })
    await waitFor(() => expect(result.current.aiError).toBe('No Anthropic API key configured.'))
  })
})

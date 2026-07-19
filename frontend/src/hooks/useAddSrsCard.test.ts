import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAddSrsCard } from './useAddSrsCard'

describe('useAddSrsCard', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('posts fen/best_move_san/context and sets ok on success', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAddSrsCard())
    act(() => result.current.addCard('fen1', 'e4', 'e4 e5'))
    await waitFor(() => expect(result.current.status).toBe('ok'))
    const [url, init] = fetchMock.mock.calls[0]
    expect(url as string).toContain('/api/opening-tree/srs')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ fen: 'fen1', best_move_san: 'e4', context: 'e4 e5' })
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useAddSrsCard())
    act(() => result.current.addCard('fen1', 'e4'))
    await waitFor(() => expect(result.current.status).toBe('error'))
  })
})

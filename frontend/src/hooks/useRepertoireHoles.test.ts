import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useRepertoireHoles } from './useRepertoireHoles'

describe('useRepertoireHoles', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches with minAppearances and topN as query params', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => [] }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useRepertoireHoles(5, 20))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchMock.mock.calls[0][0]).toContain('min_appearances=5')
    expect(fetchMock.mock.calls[0][0]).toContain('top_n=20')
    expect(result.current.holes).toEqual([])
  })
})

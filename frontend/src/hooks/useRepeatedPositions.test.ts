import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useRepeatedPositions } from './useRepeatedPositions'

function mockFetchSuccess(body: unknown) {
  return vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useRepeatedPositions', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches with the given topN and refetches when topN changes', async () => {
    const fetchMock = mockFetchSuccess([])
    vi.stubGlobal('fetch', fetchMock)
    const { result, rerender } = renderHook(({ topN }) => useRepeatedPositions(topN), {
      initialProps: { topN: 20 },
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchMock.mock.calls[0][0]).toContain('top_n=20')

    rerender({ topN: 30 })
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2))
    expect(fetchMock.mock.calls[1][0]).toContain('top_n=30')
  })
})

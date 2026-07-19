import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePatternsSummary } from './usePatternsSummary'

const BODY = [
  {
    tab_id: 'clock-time',
    label: 'Clock & Time',
    headline: 'Blunder rate peaks at 12.0% with "critical (<5%)" clock left',
    detail: 'vs. 3.0% with "plenty (60-100%)" clock left',
  },
]

describe('usePatternsSummary', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading and fetches once on mount', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => BODY }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePatternsSummary())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.cards).toEqual(BODY)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/patterns/summary')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePatternsSummary())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.cards).toBeNull()
  })
})

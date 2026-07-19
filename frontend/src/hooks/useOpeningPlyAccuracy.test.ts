import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningPlyAccuracy } from './useOpeningPlyAccuracy'

describe('useOpeningPlyAccuracy', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when openingFamily or playerColor is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useOpeningPlyAccuracy(null, null, 3))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches with URL-encoded family/color and minAppearances', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => [] }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningPlyAccuracy("Queen's Gambit", 'white', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain(`opening_family=${encodeURIComponent("Queen's Gambit")}`)
    expect(url).toContain('player_color=white')
    expect(url).toContain('min_appearances=3')
  })
})

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningsTable } from './useOpeningsTable'

const SAMPLE_ROWS = [
  { opening_family: 'Sicilian Defense', player_color: 'white', n: 42, win_pct: 55.0,
    draw_pct: 10.0, acpl: 32.5, n_analyzed: 20 },
]

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useOpeningsTable', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts loading, then resolves with rows', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_ROWS))
    const { result } = renderHook(() => useOpeningsTable())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(false)
    expect(result.current.openings).toEqual(SAMPLE_ROWS)
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useOpeningsTable())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.openings).toBeNull()
  })
})

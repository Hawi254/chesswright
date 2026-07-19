import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useFamilyDeepDive } from './useFamilyDeepDive'

const SAMPLE_TREND = [{ period: 8072, label: '2018 Q1', n_games: 10, n_wins: 6, win_pct: 60 }]
const SAMPLE_ACPL = [{ label: '2018 Q1', n_moves: 40, n_games: 8, acpl: 35.2, n_total_games: 10, coverage_pct: 80 }]

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    if (path === '/api/evolution/family-trend') return Promise.resolve({ ok: true, json: async () => SAMPLE_TREND })
    if (path === '/api/evolution/family-acpl') return Promise.resolve({ ok: true, json: async () => SAMPLE_ACPL })
    throw new Error(`unexpected path ${path}`)
  })
}

describe('useFamilyDeepDive', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does not fetch when family is null', () => {
    const fetchMock = mockFetchSuccess()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useFamilyDeepDive(null, 'white', null))
    expect(result.current.loading).toBe(false)
    expect(result.current.deepDive).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches trend and acpl together once family is set', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useFamilyDeepDive('Sicilian Defense', 'white', null))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.deepDive?.trend).toEqual(SAMPLE_TREND)
    expect(result.current.deepDive?.acpl).toEqual(SAMPLE_ACPL)
  })

  it('does not refetch when family stays the same across a rerender', async () => {
    const fetchMock = mockFetchSuccess()
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(
      ({ family }) => useFamilyDeepDive(family, 'white', null),
      { initialProps: { family: 'Sicilian Defense' as string | null } },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2)) // trend + acpl
    rerender({ family: 'Sicilian Defense' })
    expect(fetchMock).toHaveBeenCalledTimes(2) // unchanged -- no refetch
  })

  it('reports an error state if a request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useFamilyDeepDive('Sicilian Defense', 'white', null))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.deepDive).toBeNull()
  })
})

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEvolutionData } from './useEvolutionData'

const SAMPLE_RATING_TRAJECTORY = [
  { year: 2024, avg_rating: 1400, n_games: 50 },
  { year: 2025, avg_rating: 1500, n_games: 60 },
]
const SAMPLE_ACPL_TRAJECTORY = [
  { year: 2024, acpl: 45.2, n_games: 20, n_total_games: 50, coverage_pct: 40.0 },
]

const RESPONSES: Record<string, unknown> = {
  '/api/overview/rating-trajectory': SAMPLE_RATING_TRAJECTORY,
  '/api/overview/acpl-trajectory': SAMPLE_ACPL_TRAJECTORY,
}

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
  })
}

describe('useEvolutionData', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useEvolutionData())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('populates both trajectories when every request succeeds', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useEvolutionData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.ratingTrajectory).toEqual(SAMPLE_RATING_TRAJECTORY)
    expect(result.current.acplTrajectory).toEqual(SAMPLE_ACPL_TRAJECTORY)
  })

  it('reports an error state if a request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useEvolutionData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.ratingTrajectory).toBeNull()
    expect(result.current.acplTrajectory).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useEvolutionData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})

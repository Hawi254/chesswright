import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOverviewData } from './useOverviewData'

const SAMPLE_STATS = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000,
}
const SAMPLE_RATING_SNAPSHOT = { current_rating: 1500, peak_rating: 1550 }
const SAMPLE_STREAK = { outcome: 'win', length: 3 }
const SAMPLE_FINDINGS = [
  { title: 'Sharp attacker', headline: 'h', detail: 'd', polarity: 'strength',
    severity: 'medium', category: 'tactical' },
]
const SAMPLE_NARRATIVE_RESPONSE = { narrative: 'Test narrative text.' }

const RESPONSES: Record<string, unknown> = {
  '/api/overview/headline-stats': SAMPLE_STATS,
  '/api/overview/rating-snapshot': SAMPLE_RATING_SNAPSHOT,
  '/api/overview/current-streak': SAMPLE_STREAK,
  '/api/overview/career-findings': SAMPLE_FINDINGS,
  '/api/overview/narrative': SAMPLE_NARRATIVE_RESPONSE,
}

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
  })
}

describe('useOverviewData', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useOverviewData())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    // Let the in-flight fetch settle before the test ends, so its state
    // update isn't left dangling into the next test (would otherwise log
    // an "update not wrapped in act" warning).
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('populates all fields when every request succeeds', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useOverviewData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.stats).toEqual(SAMPLE_STATS)
    expect(result.current.ratingSnapshot).toEqual(SAMPLE_RATING_SNAPSHOT)
    expect(result.current.streak).toEqual(SAMPLE_STREAK)
    expect(result.current.findings).toEqual(SAMPLE_FINDINGS)
    expect(result.current.narrative).toBe('Test narrative text.')
  })

  it('reports a page-level error if every request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useOverviewData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.stats).toBeNull()
    expect(result.current.narrative).toBeNull()
  })

  it('reports a page-level error if a single request returns not-ok', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/overview/narrative') {
        return Promise.resolve({ ok: false, status: 500 })
      }
      return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
    }))
    const { result } = renderHook(() => useOverviewData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})

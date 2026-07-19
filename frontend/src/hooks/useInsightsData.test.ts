import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useInsightsData } from './useInsightsData'

const SAMPLE_STATS = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000, implied_rating: 1973, rating_confidence: 'high',
}
const SAMPLE_FINDINGS = [
  { title: 'Sharp attacker', headline: 'h', detail: 'd', polarity: 'strength',
    severity: 'medium', category: 'tactical', confidence: 'high', sample_size: 200 },
]
const SAMPLE_RATING_SNAPSHOT = { current_rating: 1850, peak_rating: 1920 }
const SAMPLE_TREND = {
  compared_to_date: '2026-04-15',
  acpl_delta: -3.2, blunder_rate_delta: -0.8, win_pct_delta: 2.1, implied_rating_delta: 45,
}

const RESPONSES: Record<string, unknown> = {
  '/api/overview/headline-stats': SAMPLE_STATS,
  '/api/overview/career-findings': SAMPLE_FINDINGS,
  '/api/overview/rating-snapshot': SAMPLE_RATING_SNAPSHOT,
  '/api/overview/headline-trend': SAMPLE_TREND,
}

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
  })
}

describe('useInsightsData', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useInsightsData())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it('populates stats, findings, ratingSnapshot, and trend when all requests succeed', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useInsightsData())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(false)
    expect(result.current.stats).toEqual(SAMPLE_STATS)
    expect(result.current.findings).toEqual(SAMPLE_FINDINGS)
    expect(result.current.ratingSnapshot).toEqual(SAMPLE_RATING_SNAPSHOT)
    expect(result.current.trend).toEqual(SAMPLE_TREND)
  })

  it('reports an error if any request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useInsightsData())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.stats).toBeNull()
    expect(result.current.findings).toBeNull()
    expect(result.current.ratingSnapshot).toBeNull()
    expect(result.current.trend).toBeNull()
  })
})

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEvolutionSummary } from './useEvolutionSummary'

const SAMPLE_RESPONSE = {
  total_games: 20,
  n_periods: 8,
  composition: { shares: [{ period: 8072, label: '2018 Q1', family: 'A', n_games: 10, share: 100 }], top: ['A'] },
  ledger: [{ family: 'A', status: 'stable', n_games_total: 20, share_early: 50, share_late: 50,
             win_early: 40, win_late: 60, n_early: 10, n_late: 10, first_label: '2018 Q1',
             last_label: '2019 Q4', adopted_label: '2018 Q1', dropped_label: '2019 Q4' }],
  strips: [{ period: 8072, label: '2018 Q1', family: 'A', n_games: 10, share: 100 }],
}

function mockFetchSuccess() {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => SAMPLE_RESPONSE }))
}

describe('useEvolutionSummary', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useEvolutionSummary('white', null, 'family'))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it('maps the snake_case response into the camelCase summary shape', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useEvolutionSummary('white', null, 'family'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.summary?.totalGames).toBe(20)
    expect(result.current.summary?.nPeriods).toBe(8)
    expect(result.current.summary?.ledger).toEqual(SAMPLE_RESPONSE.ledger)
  })

  it('omits time_control from the query string when null', async () => {
    const fetchMock = mockFetchSuccess()
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useEvolutionSummary('white', null, 'family'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).not.toContain('time_control')
    expect(url).toContain('color=white')
    expect(url).toContain('grouping=family')
  })

  it('includes time_control in the query string when set', async () => {
    const fetchMock = mockFetchSuccess()
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useEvolutionSummary('white', 'blitz', 'family'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('time_control=blitz')
  })

  it('refetches when the color argument changes', async () => {
    const fetchMock = mockFetchSuccess()
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(
      ({ color }) => useEvolutionSummary(color, null, 'family'),
      { initialProps: { color: 'white' as const } },
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ color: 'black' as const })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useEvolutionSummary('white', null, 'family'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })
})

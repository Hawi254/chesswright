import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpponentPrepOpponents, useOpponentPrepReport } from './useOpponentPrepReport'

const REPORT_BODY = {
  gamesAnalyzed: 12, colorSplit: { white: 7, black: 5 },
  dateRange: { from: '2026-01-01', to: '2026-06-01' },
  repertoire: [
    { color: 'black', opening: 'Sicilian Defense', n_games: 5, score_pct: 40.0, avg_cpl: 55.0, blunder_pct: 12.0 },
  ],
}

describe('useOpponentPrepReport', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns null report when username is null', async () => {
    const { result } = renderHook(() => useOpponentPrepReport(null))
    expect(result.current.report).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('fetches the report for a given username', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => REPORT_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepReport('DrNykterstein'))
    await act(async () => {})

    expect(result.current.report?.gamesAnalyzed).toBe(12)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/opponent-prep/report/DrNykterstein'))
  })

  it('sets error on a failed fetch', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 404 }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepReport('nobody'))
    await act(async () => {})

    expect(result.current.error).toBe(true)
    expect(result.current.report).toBeNull()
  })
})

describe('useOpponentPrepOpponents', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches the previously-scouted opponents list', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ opponents: ['alice', 'bob'] }) }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepOpponents())
    await act(async () => {})

    expect(result.current.opponents).toEqual(['alice', 'bob'])
  })
})

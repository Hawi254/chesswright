import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEndingTreeDrilldown } from './useEndingTreeDrilldown'

const RAW_RESPONSE = {
  game_ids: ['g1', 'g2'],
  total: 5,
  secondary_chart: [{ label: 'Knight', n: 2, pct: 100.0 }],
  secondary_chart_kind: 'piece',
}

describe('useEndingTreeDrilldown', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when path is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingTreeDrilldown(null, null))
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not fetch when path is "root"', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingTreeDrilldown('root', null))
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches and camelCases the response once path is set', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => RAW_RESPONSE }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingTreeDrilldown('loss/checkmate', null))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.drilldown).toEqual({
      gameIds: ['g1', 'g2'], total: 5,
      secondaryChart: [{ label: 'Knight', n: 2, pct: 100.0 }],
      secondaryChartKind: 'piece',
    })
    expect(fetchMock.mock.calls[0][0]).toContain('path=loss%2Fcheckmate')
  })

  it('includes time_control in the URL when set', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => RAW_RESPONSE }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useEndingTreeDrilldown('loss/checkmate', 'bullet'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toContain('time_control=bullet')
  })
})

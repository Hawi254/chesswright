import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningTreeChanges } from './useOpeningTreeChanges'

const CHANGES = [{ ply: 3, zobrist_hash: '7', path: ['e4', 'e5', 'Nc3'], before_san: 'Nc3', before_share: 100,
  before_win_pct: 60, before_total: 5, after_san: 'Nf3', after_share: 100, after_win_pct: 66.7, after_total: 6 }]

describe('useOpeningTreeChanges', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches changes with color/min_games query params', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => CHANGES }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningTreeChanges('w', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.changes).toEqual(CHANGES)
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('/api/opening-tree/changes')
    expect(url).toContain('color=w')
    expect(url).toContain('min_games=3')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useOpeningTreeChanges('w', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.changes).toEqual([])
  })
})

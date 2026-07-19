import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningTreeMap } from './useOpeningTreeMap'

const MAP = { ids: ['root'], labels: ['Start'], parents: [''], values: [10], win_pct: [50], has_flip: [false] }

describe('useOpeningTreeMap', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the map with color/min_games query params', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => MAP }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningTreeMap('w', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.map).toEqual(MAP)
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('/api/opening-tree/map')
    expect(url).toContain('color=w')
    expect(url).toContain('min_games=3')
  })

  it('sets error on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useOpeningTreeMap('w', 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.map).toBeNull()
  })

  it('refetches when minGames changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => MAP }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(({ mg }) => useOpeningTreeMap('w', mg), { initialProps: { mg: 3 } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ mg: 5 })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('does not fetch when enabled is false', () => {
    // Found live 2026-07-16: the whole-page Pro upsell still fired
    // opening-tree fetches (403s in the console) because hooks must be
    // called unconditionally (Rules of Hooks) -- the page's own gating
    // only controlled render output, not whether the hook's effect ran.
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningTreeMap('w', 3, false))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(result.current.map).toBeNull()
    expect(result.current.loading).toBe(false)
  })
})

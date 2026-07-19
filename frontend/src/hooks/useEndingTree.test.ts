import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEndingTree } from './useEndingTree'

const TREE = { ids: ['root'], labels: ['All games'], parents: [''], values: [0] }

describe('useEndingTree', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the unfiltered tree when timeControl is null', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => TREE }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingTree(null))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.tree).toEqual(TREE)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/game-endings/tree')
    expect(fetchMock.mock.calls[0][0]).not.toContain('time_control')
  })

  it('includes time_control in the URL when set', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => TREE }))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useEndingTree('bullet'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toContain('/api/game-endings/tree?time_control=bullet')
  })

  it('sets error on a non-ok response', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEndingTree(null))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.tree).toBeNull()
  })

  it('refetches when timeControl changes', async () => {
    const fetchMock = vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => TREE }))
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = renderHook(({ tc }) => useEndingTree(tc), { initialProps: { tc: null as string | null } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    rerender({ tc: 'blitz' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock.mock.calls[1][0]).toContain('/api/game-endings/tree?time_control=blitz')
  })
})

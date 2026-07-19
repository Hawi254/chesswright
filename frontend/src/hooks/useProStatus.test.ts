import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useProStatus } from './useProStatus'

describe('useProStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts loading, then reports active status on mount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ active: true }) }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useProStatus())
    expect(result.current.loading).toBe(true)
    expect(result.current.active).toBe(false)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.active).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/pro-status'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('fails closed (active: false, loading: false) on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))

    const { result } = renderHook(() => useProStatus())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.active).toBe(false)
  })

  it('fails closed on network error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network error'))))

    const { result } = renderHook(() => useProStatus())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.active).toBe(false)
  })
})

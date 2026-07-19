import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCoachingPlanStatus } from './useCoachingPlanStatus'

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useCoachingPlanStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ cached: false }))
    const { result } = renderHook(() => useCoachingPlanStatus())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('reports cached: true when the API says a plan is already cached', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ cached: true }))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.cached).toBe(true)
  })

  it('reports cached: false when no plan has been generated yet', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ cached: false }))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.cached).toBe(false)
  })

  it('reports an error state if the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.cached).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})

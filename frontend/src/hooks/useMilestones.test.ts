import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMilestones } from './useMilestones'

const SAMPLE_MILESTONES = [
  { achievement_id: 'first_win', name: 'First Win',
    description: 'Win your first recorded game.', unlocked_at: '2026-01-01T00:00:00' },
]

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useMilestones', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_MILESTONES))
    const { result } = renderHook(() => useMilestones())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('populates milestones when the request succeeds', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess(SAMPLE_MILESTONES))
    const { result } = renderHook(() => useMilestones())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.milestones).toEqual(SAMPLE_MILESTONES)
  })

  it('returns an empty array when there are no unlocked achievements', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess([]))
    const { result } = renderHook(() => useMilestones())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.milestones).toEqual([])
  })

  it('reports an error state if the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useMilestones())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.milestones).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useMilestones())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})

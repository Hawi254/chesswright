import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEngineProfiles } from './useEngineProfiles'

describe('useEngineProfiles', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the profile list on mount', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ profiles: ['a', 'b'] }) })))
    const { result } = renderHook(() => useEngineProfiles())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.profiles).toEqual(['a', 'b'])
  })

  it('saveProfile() POSTs the name and updates the list', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ profiles: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ profiles: ['deep-analysis'] }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineProfiles())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.saveProfile('deep-analysis')
    })
    expect(result.current.profiles).toEqual(['deep-analysis'])
  })

  it('applyProfile() sets applyError on a 404', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ profiles: ['a'] }) })
      .mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({ detail: "No engine profile named 'x'." }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineProfiles())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.applyProfile('x')
    })
    expect(result.current.applyError).toBe("No engine profile named 'x'.")
  })

  it('deleteProfile() DELETEs and updates the list', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ profiles: ['a'] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ profiles: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineProfiles())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.deleteProfile('a')
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/engine-profiles/a'),
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(result.current.profiles).toEqual([])
  })
})

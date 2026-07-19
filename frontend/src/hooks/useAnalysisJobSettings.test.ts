import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAnalysisJobSettings } from './useAnalysisJobSettings'

const SETTINGS = {
  depth: 18, multipv: 3, threads: 4, hashMb: 256, maxGames: null, maxDuration: null,
}

describe('useAnalysisJobSettings', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches settings on mount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => SETTINGS }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.settings).toEqual(SETTINGS)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/analysis-jobs/settings'))
  })

  it('sets error on a failed initial fetch', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })

  it('save() PUTs the snake_case body and updates settings on success', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SETTINGS })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))

    const next = { depth: 20, multipv: 4, threads: 8, hashMb: 512, maxGames: 100, maxDuration: '2h' }
    await act(async () => {
      await result.current.save(next)
    })

    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/analysis-jobs/settings'),
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          depth: 20, multipv: 4, max_games: 100, max_duration: '2h', threads: 8, hash_mb: 512,
        }),
      }),
    )
    expect(result.current.settings).toEqual(next)
    expect(result.current.saving).toBe(false)
    expect(result.current.saveError).toBeNull()
  })

  it('save() sets saveError from the response detail on a 409', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SETTINGS })
      .mockResolvedValueOnce({
        ok: false, status: 409,
        json: async () => ({ detail: 'Settings are read-only while a batch is running.' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysisJobSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.save(SETTINGS)
    })

    expect(result.current.saveError).toBe('Settings are read-only while a batch is running.')
    expect(result.current.saving).toBe(false)
  })
})

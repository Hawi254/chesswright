import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEngineSettings } from './useEngineSettings'

const ENGINE = {
  path: '/usr/games/stockfish',
  detectedPath: '/usr/games/stockfish',
  live: { timeSec: 0.5, depth: 20, threads: 1, hashMb: 32, storeThreshold: 20, useLichessCloudEval: true },
}

describe('useEngineSettings', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches engine settings on mount', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ENGINE })))
    const { result } = renderHook(() => useEngineSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.engine).toEqual(ENGINE)
  })

  it('setPath() POSTs the new path and updates engine on success', async () => {
    const updated = { ...ENGINE, path: '/opt/stockfish' }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ENGINE })
      .mockResolvedValueOnce({ ok: true, json: async () => updated })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.setPath('/opt/stockfish')
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/engine/path'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.current.engine).toEqual(updated)
  })

  it('setPath() sets pathError on a 400', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ENGINE })
      .mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ detail: 'not a valid engine' }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.setPath('/bogus')
    })
    expect(result.current.pathError).toBe('not a valid engine')
  })

  it('redetect() POSTs and updates engine on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ENGINE })
      .mockResolvedValueOnce({ ok: true, json: async () => ENGINE })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.redetect()
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/engine/redetect'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('saveLive() POSTs the live settings and updates engine', async () => {
    const nextLive = { ...ENGINE.live, depth: 30 }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ENGINE })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...ENGINE, live: nextLive }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.saveLive(nextLive)
    })
    expect(result.current.engine?.live).toEqual(nextLive)
  })

  it('reset() POSTs and updates engine', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ENGINE })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...ENGINE, path: null } ) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useEngineSettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.reset()
    })
    expect(result.current.engine?.path).toBeNull()
  })
})

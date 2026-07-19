import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useOpponentPrepStatus } from './useOpponentPrepStatus'

const IDLE_BODY = { status: 'idle', username: null, step: null, error: null }

describe('useOpponentPrepStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('fetches immediately on mount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => IDLE_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepStatus())
    await act(async () => {})

    expect(result.current.loading).toBe(false)
    expect(result.current.data?.status).toBe('idle')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/opponent-prep/status'))
  })

  it('refetches every 2 seconds', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => IDLE_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useOpponentPrepStatus())
    await act(async () => {})
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('sets connectionLost after a failed poll tick, keeps last-known data', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => IDLE_BODY })
      .mockRejectedValueOnce(new Error('network down'))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepStatus())
    await act(async () => {})
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })

    expect(result.current.connectionLost).toBe(true)
    expect(result.current.data?.status).toBe('idle')
  })

  it('stops polling on unmount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => IDLE_BODY }))
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = renderHook(() => useOpponentPrepStatus())
    await act(async () => {})
    unmount()

    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

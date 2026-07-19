import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useChesscomAccount } from './useChesscomAccount'

describe('useChesscomAccount', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the current username on mount', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ username: 'my_account' }) })))
    const { result } = renderHook(() => useChesscomAccount())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.username).toBe('my_account')
  })

  it('connect() POSTs the username and updates state', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ username: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ username: 'new_account' }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChesscomAccount())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.connect('new_account')
    })
    expect(result.current.username).toBe('new_account')
  })

  it('disconnect() DELETEs and clears the username', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ username: 'my_account' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChesscomAccount())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.disconnect()
    })
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining('/api/settings/chesscom'), expect.objectContaining({ method: 'DELETE' }))
    expect(result.current.username).toBeNull()
  })

  it('syncNow() sets pendingError on failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ username: 'my_account' }) })
      .mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({ detail: 'user not found' }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useChesscomAccount())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.syncNow()
    })
    expect(result.current.pendingError).toBe('user not found')
  })
})

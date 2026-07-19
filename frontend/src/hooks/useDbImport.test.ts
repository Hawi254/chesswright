import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDbImport } from './useDbImport'

describe('useDbImport', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('startImport() POSTs the path and stores the pending id + suggestion', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ pendingId: 'abc123', suggestedUsername: 'me' }) })),
    )
    const { result } = renderHook(() => useDbImport())
    await act(async () => {
      await result.current.startImport('/path/to/db.sqlite')
    })
    expect(result.current.pending).toEqual({ pendingId: 'abc123', suggestedUsername: 'me' })
  })

  it('startImport() sets importError on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 400, json: async () => ({ detail: 'not a valid database' }) })),
    )
    const { result } = renderHook(() => useDbImport())
    await act(async () => {
      await result.current.startImport('/bogus')
    })
    expect(result.current.importError).toBe('not a valid database')
  })

  it('confirmImport() posts pendingId + username and clears pending on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ pendingId: 'abc123', suggestedUsername: 'me' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useDbImport())
    await act(async () => {
      await result.current.startImport('/path/to/db.sqlite')
    })
    await act(async () => {
      await result.current.confirmImport('my_username')
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/db-import/confirm'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ pending_id: 'abc123', username: 'my_username' }),
      }),
    )
    expect(result.current.pending).toBeNull()
  })

  it('cancelImport() posts pendingId and clears pending', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ pendingId: 'abc123', suggestedUsername: 'me' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useDbImport())
    await act(async () => {
      await result.current.startImport('/path/to/db.sqlite')
    })
    await act(async () => {
      await result.current.cancelImport()
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/db-import/cancel'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ pending_id: 'abc123' }) }),
    )
    expect(result.current.pending).toBeNull()
  })
})

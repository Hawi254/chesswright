import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useApiKeySettings } from './useApiKeySettings'

const STATUS = { configured: true, masked: 'sk-ant...7890', secureBackend: true }

describe('useApiKeySettings', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches status on mount', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => STATUS })))
    const { result } = renderHook(() => useApiKeySettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.status).toEqual(STATUS)
  })

  it('saveKey() POSTs the key and refetches status on success', async () => {
    const updated = { configured: true, masked: 'sk-ant...wxyz', secureBackend: true }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ configured: false, masked: null, secureBackend: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, securelyStored: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => updated })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useApiKeySettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.saveKey('sk-ant-newkeywxyz')
    })
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/api/settings/api-key'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ key: 'sk-ant-newkeywxyz' }) }),
    )
    expect(result.current.status).toEqual(updated)
  })

  it('saveKey() sets saveError on a 400', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ configured: false, masked: null, secureBackend: true }) })
      .mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ detail: 'API key is required.' }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useApiKeySettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.saveKey('   ')
    })
    expect(result.current.saveError).toBe('API key is required.')
  })

  it('removeKey() DELETEs and refetches status', async () => {
    const cleared = { configured: false, masked: null, secureBackend: true }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => STATUS })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => cleared })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useApiKeySettings())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.removeKey()
    })
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/api/settings/api-key'),
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(result.current.status).toEqual(cleared)
  })
})

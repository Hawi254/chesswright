import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useProLicense } from './useProLicense'

const LICENSE = { available: true, configured: true, masked: 'cwpro-ab...1234', purchaseEmail: 'buyer@example.com' }

describe('useProLicense', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches active status and license detail on mount', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => LICENSE })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useProLicense())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.active).toBe(true)
    expect(result.current.license).toEqual(LICENSE)
  })

  it('activate() posts the key and sets activateMessage on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active: false }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ available: true, configured: false, masked: null, purchaseEmail: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, message: 'License activated.' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => LICENSE })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useProLicense())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.activate('valid-key')
    })
    expect(result.current.activateMessage).toBe('License activated.')
    expect(result.current.active).toBe(true)
  })

  it('activate() sets activateError on failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active: false }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ available: true, configured: false, masked: null, purchaseEmail: null }) })
      .mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ detail: 'Invalid license key.' }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useProLicense())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.activate('wrong-key')
    })
    expect(result.current.activateError).toBe('Invalid license key.')
  })

  it('deactivate() posts and refreshes status', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => LICENSE })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ active: false }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ available: true, configured: false, masked: null, purchaseEmail: null }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useProLicense())
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.deactivate()
    })
    expect(result.current.active).toBe(false)
  })
})

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSettingsResource } from './useSettingsResource'

interface Sample {
  utcOffsetHours: number
  minSampleSize: number
}

const SAMPLE: Sample = { utcOffsetHours: 0, minSampleSize: 20 }

describe('useSettingsResource', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches the value on mount', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => SAMPLE }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useSettingsResource<Sample>('/api/settings/analytics'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.value).toEqual(SAMPLE)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/settings/analytics'))
  })

  it('sets error on a failed initial fetch', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useSettingsResource<Sample>('/api/settings/analytics'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })

  it('save() POSTs the value and updates state on success', async () => {
    const next = { utcOffsetHours: 5, minSampleSize: 10 }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SAMPLE })
      .mockResolvedValueOnce({ ok: true, json: async () => next })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useSettingsResource<Sample>('/api/settings/analytics'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.save(next)
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/analytics'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify(next) }),
    )
    expect(result.current.value).toEqual(next)
    expect(result.current.saveError).toBeNull()
  })

  it('save() sets saveError from the response detail on failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SAMPLE })
      .mockResolvedValueOnce({ ok: false, status: 422, json: async () => ({ detail: 'out of bounds' }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useSettingsResource<Sample>('/api/settings/analytics'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.save(SAMPLE)
    })
    expect(result.current.saveError).toBe('out of bounds')
  })

  it('reset() POSTs to the reset endpoint and updates state', async () => {
    const reset = { utcOffsetHours: 0, minSampleSize: 20 }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SAMPLE })
      .mockResolvedValueOnce({ ok: true, json: async () => reset })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() =>
      useSettingsResource<Sample>('/api/settings/analytics', '/api/settings/analytics/reset'),
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.reset()
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings/analytics/reset'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result.current.value).toEqual(reset)
  })
})

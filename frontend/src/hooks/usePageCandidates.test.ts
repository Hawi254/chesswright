import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePageCandidates } from './usePageCandidates'
import { STATIC_CANDIDATES } from '../lib/navCandidates'

describe('usePageCandidates', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses the API result when the fetch succeeds', async () => {
    const apiResult = [{ category: 'page', title: 'From API', url_path: 'from-api' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => apiResult,
    }))

    const { result } = renderHook(() => usePageCandidates())

    await waitFor(() => {
      expect(result.current.candidates).toEqual(apiResult)
    })
    expect(result.current.usingFallback).toBe(false)
  })

  it('falls back to STATIC_CANDIDATES when the fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    const { result } = renderHook(() => usePageCandidates())

    await waitFor(() => {
      expect(result.current.usingFallback).toBe(true)
    })
    expect(result.current.candidates).toEqual(STATIC_CANDIDATES)
  })

  it('falls back to STATIC_CANDIDATES when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    const { result } = renderHook(() => usePageCandidates())

    await waitFor(() => {
      expect(result.current.usingFallback).toBe(true)
    })
    expect(result.current.candidates).toEqual(STATIC_CANDIDATES)
  })
})

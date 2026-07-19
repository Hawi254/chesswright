import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePositionFen } from './usePositionFen'

describe('usePositionFen', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when ply or zobristHash is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => usePositionFen(null, null))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('resolves with the fen on success', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ fen: 'startpos' }) })))
    const { result } = renderHook(() => usePositionFen(4, '12345'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.fen).toBe('startpos')
    expect(result.current.error).toBe(false)
  })

  it('treats a 404 as fen:null, not an error state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 404 })))
    const { result } = renderHook(() => usePositionFen(4, '999'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.fen).toBeNull()
    expect(result.current.error).toBe(false)
  })

  it('treats a non-404 failure as an error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => usePositionFen(4, '999'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
  })
})

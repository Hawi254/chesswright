import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningJump } from './useOpeningJump'

describe('useOpeningJump', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('resolves a path on success', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => ({ path: ['e4', 'c5'] }) })))
    const { result } = renderHook(() => useOpeningJump('w'))
    act(() => result.current.jump('Sicilian Defense'))
    await waitFor(() => expect(result.current.status).toBe('ok'))
    expect(result.current.path).toEqual(['e4', 'c5'])
  })

  it('sets not_found on a 404', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 404, json: async () => ({}) })))
    const { result } = renderHook(() => useOpeningJump('w'))
    act(() => result.current.jump('Made Up Opening'))
    await waitFor(() => expect(result.current.status).toBe('not_found'))
    expect(result.current.path).toBeNull()
  })

  it('sets error on a non-404 failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500, json: async () => ({}) })))
    const { result } = renderHook(() => useOpeningJump('w'))
    act(() => result.current.jump('Sicilian Defense'))
    await waitFor(() => expect(result.current.status).toBe('error'))
  })
})

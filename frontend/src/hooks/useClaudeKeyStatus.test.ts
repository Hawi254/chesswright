import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useClaudeKeyStatus } from './useClaudeKeyStatus'

describe('useClaudeKeyStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches once on mount and reports availability', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ available: true }) }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useClaudeKeyStatus())
    expect(result.current.available).toBe(false)

    await waitFor(() => expect(result.current.available).toBe(true))
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/settings/claude-key-status'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('fails closed (available: false) on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))

    const { result } = renderHook(() => useClaudeKeyStatus())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(result.current.available).toBe(false)
  })

  it('fails closed on network error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network error'))))

    const { result } = renderHook(() => useClaudeKeyStatus())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(result.current.available).toBe(false)
  })
})

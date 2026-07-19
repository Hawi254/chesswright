import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpponentSwindleRate } from './useOpponentSwindleRate'

describe('useOpponentSwindleRate', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when opponentName is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpponentSwindleRate(null))
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches once opponentName is set', async () => {
    const body = { n_losses: 2, n_missed_swindle: 1, swindle_rate_pct: 50.0 }
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => body })))
    const { result } = renderHook(() => useOpponentSwindleRate('Rival'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.swindle).toEqual(body)
  })
})

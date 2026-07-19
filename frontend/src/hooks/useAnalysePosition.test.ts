import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAnalysePosition } from './useAnalysePosition'

const RESULT_A = {
  eval_cp: 35, eval_mate: null, best_move_san: 'e4', best_move_from: 'e2', best_move_to: 'e4',
  pv: ['e4', 'e5'], depth: 22, source: 'stored' as const,
}
const RESULT_B = {
  eval_cp: -10, eval_mate: null, best_move_san: 'Nf6', best_move_from: 'g8', best_move_to: 'f6',
  pv: ['Nf6'], depth: 20, source: 'live' as const,
}

function mockFetchOnce(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useAnalysePosition', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts idle, then reports the result on a successful analysis', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ status: 'ok', result: RESULT_A }))
    const { result } = renderHook(() => useAnalysePosition())
    expect(result.current.status).toBe('idle')
    expect(result.current.result).toBeNull()

    act(() => {
      result.current.analyse('FEN_A')
    })
    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.status).toBe('ok')
    expect(result.current.result).toEqual(RESULT_A)
  })

  it('resultFen tracks the FEN that produced result, and is null when result is null', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ status: 'ok', result: RESULT_A }))
    const { result } = renderHook(() => useAnalysePosition())
    expect(result.current.resultFen).toBeNull()

    act(() => {
      result.current.analyse('FEN_A')
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.resultFen).toBe('FEN_A')
    expect(result.current.result).toEqual(RESULT_A)
  })

  it('resultFen is null when the server reports a non-ok status', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ status: 'no_engine', result: null }))
    const { result } = renderHook(() => useAnalysePosition())

    act(() => {
      result.current.analyse('FEN_A')
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.resultFen).toBeNull()
  })

  it('does not re-fetch a FEN already cached from a prior analyse() call', async () => {
    const fetchMock = mockFetchOnce({ status: 'ok', result: RESULT_A })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAnalysePosition())

    act(() => {
      result.current.analyse('FEN_A')
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.analyse('FEN_A')
    })
    expect(result.current.loading).toBe(false)
    expect(result.current.result).toEqual(RESULT_A)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports a non-ok server status without populating a result', async () => {
    vi.stubGlobal('fetch', mockFetchOnce({ status: 'no_engine', result: null }))
    const { result } = renderHook(() => useAnalysePosition())

    act(() => {
      result.current.analyse('FEN_A')
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.status).toBe('no_engine')
    expect(result.current.result).toBeNull()
  })

  it('reports an error status on a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useAnalysePosition())

    act(() => {
      result.current.analyse('FEN_A')
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.status).toBe('error')
  })

  it('ignores a stale response superseded by a newer analyse() call', async () => {
    let resolveFirst: (value: unknown) => void = () => {}
    const firstPromise = new Promise((resolve) => {
      resolveFirst = resolve
    })
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => firstPromise)
      .mockImplementationOnce(() => Promise.resolve({ ok: true, json: async () => ({ status: 'ok', result: RESULT_B }) }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAnalysePosition())
    act(() => {
      result.current.analyse('FEN_A')
    })
    act(() => {
      result.current.analyse('FEN_B')
    })

    await waitFor(() => expect(result.current.status).toBe('ok'))
    expect(result.current.result).toEqual(RESULT_B)

    await act(async () => {
      resolveFirst({ ok: true, json: async () => ({ status: 'ok', result: RESULT_A }) })
      await Promise.resolve()
    })
    expect(result.current.result).toEqual(RESULT_B)
  })
})

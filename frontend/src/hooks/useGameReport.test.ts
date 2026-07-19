import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useGameReport } from './useGameReport'

describe('useGameReport', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches the cached report on mount', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => ({ report_text: '## Report', generated_at: '2026-07-14 10:00' }) }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameReport('game_1'))
    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.reportText).toBe('## Report')
    expect(result.current.generatedAt).toBe('2026-07-14 10:00')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/games/game_1/report'))
  })

  it('reports null reportText when nothing is cached', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => ({ report_text: null, generated_at: null }) }),
    ))

    const { result } = renderHook(() => useGameReport('game_1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.reportText).toBeNull()
  })

  it('generate() posts, sets generating during the call, and updates the report on success', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ report_text: null, generated_at: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ report_text: '## Fresh report', generated_at: '2026-07-14 11:00' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameReport('game_1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.generate()
    })
    expect(result.current.generating).toBe(true)

    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.reportText).toBe('## Fresh report')
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/games/game_1/report/generate'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('generate() sets error + errorStatus from the response body on 403', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ report_text: null, generated_at: null }) })
      .mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({ detail: 'Pro is not licensed' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameReport('game_1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.generate()
    })
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.error).toBe('Pro is not licensed')
    expect(result.current.errorStatus).toBe(403)
  })

  it('generate() sets errorStatus 503 on missing API key', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ report_text: null, generated_at: null }) })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'No Anthropic API key configured.' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useGameReport('game_1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.generate()
    })
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.errorStatus).toBe(503)
    expect(result.current.error).toContain('API key')
  })
})

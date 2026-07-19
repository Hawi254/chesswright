import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpponentPrepNotes } from './useOpponentPrepNotes'

describe('useOpponentPrepNotes', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns nulls when username is null', () => {
    const { result } = renderHook(() => useOpponentPrepNotes(null))
    expect(result.current.narrative).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('fetches cached narrative on mount', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => ({ narrative: 'Cached notes', generated_at: '2026-07-16' }) }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepNotes('DrNykterstein'))
    await act(async () => {})

    expect(result.current.narrative).toBe('Cached notes')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/opponent-prep/DrNykterstein/notes'))
  })

  it('generate() posts and updates narrative', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ narrative: null, generated_at: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ narrative: 'Fresh notes' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepNotes('DrNykterstein'))
    await act(async () => {})
    await act(async () => { result.current.generate() })

    expect(result.current.narrative).toBe('Fresh notes')
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/opponent-prep/DrNykterstein/notes/generate'),
      { method: 'POST' },
    )
  })

  it('generate() surfaces the error detail on failure', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ narrative: null, generated_at: null }) })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'No Anthropic API key configured.' }) })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useOpponentPrepNotes('DrNykterstein'))
    await act(async () => {})
    await act(async () => { result.current.generate() })

    expect(result.current.generateError).toBe('No Anthropic API key configured.')
  })
})

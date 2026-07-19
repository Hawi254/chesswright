import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAskStream } from './useAskStream'
import type { AskCard } from './useAskStream'

function mockSseFetch(frames: string[], status = 200, detail = 'boom') {
  let i = 0
  const encoder = new TextEncoder()
  return vi.fn(() => Promise.resolve({
    ok: status < 400,
    status,
    json: async () => ({ detail }),
    body: {
      getReader: () => ({
        read: () => {
          if (i < frames.length) {
            const chunk = frames[i]
            i += 1
            return Promise.resolve({ done: false, value: encoder.encode(chunk) })
          }
          return Promise.resolve({ done: true, value: undefined })
        },
      }),
    },
  }))
}

function mockRejectingFetch(message: string) {
  return vi.fn(() => Promise.reject(new Error(message)))
}

describe('useAskStream', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('ask() appends a streaming placeholder, patches deltas, then settles', async () => {
    vi.stubGlobal('fetch', mockSseFetch([
      'data: {"delta": "You blunder "}\n\n',
      'data: {"delta": "most in the middlegame."}\n\n',
      'data: {"done": true, "answer": "You blunder most in the middlegame."}\n\n',
    ]))

    const { result } = renderHook(() => useAskStream())
    act(() => { result.current.ask('When do I blunder most?') })

    expect(result.current.cards).toHaveLength(1)
    expect(result.current.cards[0].status).toBe('streaming')
    expect(result.current.cards[0].question).toBe('When do I blunder most?')

    await waitFor(() => expect(result.current.cards[0].status).toBe('settled'))
    expect(result.current.cards[0].answer).toBe('You blunder most in the middlegame.')
  })

  it('a frame split across two reads is still parsed correctly', async () => {
    vi.stubGlobal('fetch', mockSseFetch([
      'data: {"del',
      'ta": "partial"}\n\n',
      'data: {"done": true, "answer": "partial"}\n\n',
    ]))

    const { result } = renderHook(() => useAskStream())
    act(() => { result.current.ask('q?') })

    await waitFor(() => expect(result.current.cards[0].status).toBe('settled'))
    expect(result.current.cards[0].answer).toBe('partial')
  })

  it('persists only settled cards to localStorage, capped at 20', async () => {
    const seeded: AskCard[] = Array.from({ length: 20 }, (_, i) => ({
      id: `seed-${i}`, question: `Q${i}`, answer: `A${i}`, status: 'settled', errorMessage: null,
      askedAt: new Date(2026, 0, i + 1).toISOString(),
    }))
    window.localStorage.setItem('chesswright.ask.history', JSON.stringify(seeded))

    vi.stubGlobal('fetch', mockSseFetch([
      'data: {"delta": "new"}\n\n',
      'data: {"done": true, "answer": "new"}\n\n',
    ]))

    const { result } = renderHook(() => useAskStream())
    expect(result.current.cards).toHaveLength(20)

    act(() => { result.current.ask('one more?') })
    await waitFor(() => expect(result.current.cards[0].status).toBe('settled'))

    const stored = JSON.parse(window.localStorage.getItem('chesswright.ask.history')!) as AskCard[]
    expect(stored).toHaveLength(20)
    expect(stored[0].question).toBe('one more?')
  })

  it('hydrates cards from localStorage on mount', () => {
    const seeded: AskCard[] = [{
      id: 'seed-1', question: 'Old question', answer: 'Old answer', status: 'settled',
      errorMessage: null, askedAt: new Date(2026, 0, 1).toISOString(),
    }]
    window.localStorage.setItem('chesswright.ask.history', JSON.stringify(seeded))

    const { result } = renderHook(() => useAskStream())
    expect(result.current.cards).toEqual(seeded)
  })

  it('a card-level failure flips only that card to error and is not persisted', async () => {
    vi.stubGlobal('fetch', mockRejectingFetch('network drop'))

    const { result } = renderHook(() => useAskStream())
    act(() => { result.current.ask('q?') })

    await waitFor(() => expect(result.current.cards[0].status).toBe('error'))
    expect(result.current.cards[0].errorMessage).toBe('network drop')
    expect(window.localStorage.getItem('chesswright.ask.history')).toBe(null)
  })

  it('aborts the in-flight request on unmount', () => {
    const fetchMock = vi.fn(() => new Promise(() => {})) // never resolves
    vi.stubGlobal('fetch', fetchMock)

    const { result, unmount } = renderHook(() => useAskStream())
    act(() => { result.current.ask('q?') })

    const signal = (fetchMock.mock.calls[0][1] as RequestInit).signal as AbortSignal
    expect(signal.aborted).toBe(false)
    unmount()
    expect(signal.aborted).toBe(true)
  })

  it('clearHistory empties cards and localStorage', async () => {
    vi.stubGlobal('fetch', mockSseFetch([
      'data: {"delta": "x"}\n\n',
      'data: {"done": true, "answer": "x"}\n\n',
    ]))

    const { result } = renderHook(() => useAskStream())
    act(() => { result.current.ask('q?') })
    await waitFor(() => expect(result.current.cards[0].status).toBe('settled'))

    act(() => { result.current.clearHistory() })
    expect(result.current.cards).toEqual([])
    expect(window.localStorage.getItem('chesswright.ask.history')).toBe(JSON.stringify([]))
  })

  it('retry() re-runs the stream for the same question', async () => {
    vi.stubGlobal('fetch', mockRejectingFetch('boom'))
    const { result } = renderHook(() => useAskStream())
    act(() => { result.current.ask('q?') })
    await waitFor(() => expect(result.current.cards[0].status).toBe('error'))

    vi.stubGlobal('fetch', mockSseFetch([
      'data: {"delta": "recovered"}\n\n',
      'data: {"done": true, "answer": "recovered"}\n\n',
    ]))
    act(() => { result.current.retry(result.current.cards[0].id) })

    await waitFor(() => expect(result.current.cards[0].status).toBe('settled'))
    expect(result.current.cards[0].answer).toBe('recovered')
    expect(result.current.cards[0].question).toBe('q?')
  })
})

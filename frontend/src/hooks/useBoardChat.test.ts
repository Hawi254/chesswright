import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useBoardChat } from './useBoardChat'

describe('useBoardChat', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loadPastConversations populates pastConversations', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => ({ conversations: [{ id: 1, started_at: '2026-07-14', turn_count: 3 }] }) }),
    ))
    const { result } = renderHook(() => useBoardChat('game_1'))
    act(() => { result.current.loadPastConversations() })
    await waitFor(() => expect(result.current.pastConversations).toHaveLength(1))
    expect(result.current.pastConversations[0]).toEqual({ id: 1, started_at: '2026-07-14', turn_count: 3 })
  })

  it('resumeConversation sets conversationId, displayHistory, arrows, and a highlight record', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          display_history: [
            { role: 'user', content: 'best move?', turn_id: null },
            { role: 'assistant', content: 'Nf3.', turn_id: 5 },
          ],
          arrows: [{ from: 'g1', to: 'f3', color: '#6FA98C' }],
          highlights: [{ square: 'e5', color: '#B0584F' }],
        }),
      }),
    ))
    const { result } = renderHook(() => useBoardChat('game_1'))
    act(() => { result.current.resumeConversation(7, 'fen-here') })
    await waitFor(() => expect(result.current.conversationId).toBe(7))
    expect(result.current.displayHistory).toEqual([
      { role: 'user', content: 'best move?', turnId: null },
      { role: 'assistant', content: 'Nf3.', turnId: 5 },
    ])
    expect(result.current.arrows).toEqual([{ from: 'g1', to: 'f3', color: '#6FA98C' }])
    expect(result.current.highlights).toEqual({ e5: { background: '#B0584F' } })
  })

  it('sendMessage appends the user message immediately, then the assistant reply on success', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({ conversation_id: 3, turn_id: 9, answer_text: 'Play e4.', arrows: [], highlights: [] }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBoardChat('game_1'))

    act(() => { result.current.sendMessage('what now?', 'fen-here') })
    expect(result.current.sending).toBe(true)
    expect(result.current.displayHistory).toEqual([{ role: 'user', content: 'what now?', turnId: null }])

    await waitFor(() => expect(result.current.sending).toBe(false))
    expect(result.current.displayHistory).toEqual([
      { role: 'user', content: 'what now?', turnId: null },
      { role: 'assistant', content: 'Play e4.', turnId: 9 },
    ])
    expect(result.current.conversationId).toBe(3)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/games/game_1/board-chat/turns'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('sendMessage sets error on failure but keeps the appended user message', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false, status: 503, json: async () => ({ detail: 'No Anthropic API key configured.' }),
    })))
    const { result } = renderHook(() => useBoardChat('game_1'))
    act(() => { result.current.sendMessage('what now?', 'fen-here') })
    await waitFor(() => expect(result.current.sending).toBe(false))
    expect(result.current.error).toBe('No Anthropic API key configured.')
    expect(result.current.displayHistory).toEqual([{ role: 'user', content: 'what now?', turnId: null }])
  })

  it('trusts the server-resolved arrows field turn to turn (plan-overrides-arrows precedence lives server-side)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        conversation_id: 1, turn_id: 1, answer_text: 'Nf3.',
        arrows: [{ from: 'g1', to: 'f3', color: '#6FA98C' }], highlights: [],
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        conversation_id: 1, turn_id: 2, answer_text: 'Here is the plan.',
        arrows: [
          { from: 'e2', to: 'e4', color: 'rgba(111,169,140,1.0)' },
          { from: 'e4', to: 'e5', color: 'rgba(111,169,140,0.7)' },
        ],
        highlights: [],
      }) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBoardChat('game_1'))

    act(() => { result.current.sendMessage('best move?', 'fen-1') })
    await waitFor(() => expect(result.current.sending).toBe(false))
    expect(result.current.arrows).toEqual([{ from: 'g1', to: 'f3', color: '#6FA98C' }])

    act(() => { result.current.sendMessage('show me a plan', 'fen-1') })
    await waitFor(() => expect(result.current.sending).toBe(false))
    expect(result.current.arrows).toEqual([
      { from: 'e2', to: 'e4', color: 'rgba(111,169,140,1.0)' },
      { from: 'e4', to: 'e5', color: 'rgba(111,169,140,0.7)' },
    ])
  })

  it('sendFeedback derives question_summary from the nearest preceding user entry on a downvote', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        conversation_id: 1, turn_id: 9, answer_text: 'Play e4.', arrows: [], highlights: [],
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBoardChat('game_1'))

    act(() => { result.current.sendMessage('what now?', 'fen-here') })
    await waitFor(() => expect(result.current.sending).toBe(false))

    act(() => { result.current.sendFeedback(9, -1) })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/board-chat/turns/9/feedback'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ feedback: -1, question_summary: 'what now?' }),
      }),
    )
  })

  it('sendFeedback on a thumbs-up sends no question_summary', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        conversation_id: 1, turn_id: 9, answer_text: 'Play e4.', arrows: [], highlights: [],
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useBoardChat('game_1'))

    act(() => { result.current.sendMessage('what now?', 'fen-here') })
    await waitFor(() => expect(result.current.sending).toBe(false))

    act(() => { result.current.sendFeedback(9, 1) })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/board-chat/turns/9/feedback'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ feedback: 1, question_summary: null }),
      }),
    )
  })
})

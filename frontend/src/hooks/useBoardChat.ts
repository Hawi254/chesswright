import { useCallback, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface BoardChatDisplayEntry {
  role: 'user' | 'assistant'
  content: string
  turnId: number | null
}

export interface BoardChatPastConversation {
  id: number
  started_at: string
  turn_count: number
}

export interface BoardChatArrow {
  from: string
  to: string
  color: string
}

export interface UseBoardChatResult {
  displayHistory: BoardChatDisplayEntry[]
  conversationId: number | null
  sending: boolean
  error: string | null
  pastConversations: BoardChatPastConversation[]
  arrows: BoardChatArrow[]
  highlights: Record<string, { background: string }>
  sendMessage: (question: string, currentFen: string) => void
  loadPastConversations: () => void
  resumeConversation: (conversationId: number, currentFen: string) => void
  sendFeedback: (turnId: number, feedback: 1 | -1) => void
}

interface RawHighlight {
  square: string
  color: string
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

function toHighlightRecord(highlights: RawHighlight[]): Record<string, { background: string }> {
  return Object.fromEntries(highlights.map((h) => [h.square, { background: h.color }]))
}

export function useBoardChat(gameId: string): UseBoardChatResult {
  const [displayHistory, setDisplayHistory] = useState<BoardChatDisplayEntry[]>([])
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pastConversations, setPastConversations] = useState<BoardChatPastConversation[]>([])
  const [arrows, setArrows] = useState<BoardChatArrow[]>([])
  const [highlights, setHighlights] = useState<Record<string, { background: string }>>({})

  const loadPastConversations = useCallback(() => {
    fetch(`${API_BASE}/api/games/${gameId}/board-chat/conversations`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ conversations: BoardChatPastConversation[] }>
      })
      .then((body) => setPastConversations(body.conversations))
      .catch(() => setPastConversations([]))
  }, [gameId])

  const resumeConversation = useCallback((targetConversationId: number, currentFen: string) => {
    const url = `${API_BASE}/api/games/${gameId}/board-chat/conversations/${targetConversationId}`
      + `?current_fen=${encodeURIComponent(currentFen)}`
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{
          display_history: Array<{ role: 'user' | 'assistant'; content: string; turn_id: number | null }>
          arrows: BoardChatArrow[]
          highlights: RawHighlight[]
        }>
      })
      .then((body) => {
        setConversationId(targetConversationId)
        setDisplayHistory(body.display_history.map((e) => ({ role: e.role, content: e.content, turnId: e.turn_id })))
        setArrows(body.arrows)
        setHighlights(toHighlightRecord(body.highlights))
      })
      .catch(() => setError('Failed to resume conversation. Try again.'))
  }, [gameId])

  const sendMessage = useCallback((question: string, currentFen: string) => {
    setSending(true)
    setError(null)
    setDisplayHistory((prev) => [...prev, { role: 'user', content: question, turnId: null }])

    fetch(`${API_BASE}/api/games/${gameId}/board-chat/turns`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, question, current_fen: currentFen }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await errorDetail(r))
        return r.json() as Promise<{
          conversation_id: number
          turn_id: number
          answer_text: string
          arrows: BoardChatArrow[]
          highlights: RawHighlight[]
        }>
      })
      .then((body) => {
        setConversationId(body.conversation_id)
        setDisplayHistory((prev) => [...prev, { role: 'assistant', content: body.answer_text, turnId: body.turn_id }])
        setArrows(body.arrows)
        setHighlights(toHighlightRecord(body.highlights))
        setSending(false)
      })
      .catch((err: Error) => {
        setSending(false)
        setError(err.message)
      })
  }, [gameId, conversationId])

  const sendFeedback = useCallback((turnId: number, feedback: 1 | -1) => {
    let questionSummary: string | null = null
    if (feedback === -1) {
      const idx = displayHistory.findIndex((e) => e.turnId === turnId)
      const scope = idx === -1 ? displayHistory : displayHistory.slice(0, idx)
      const preceding = [...scope].reverse().find((e) => e.role === 'user')
      questionSummary = preceding?.content ?? null
    }
    fetch(`${API_BASE}/api/board-chat/turns/${turnId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback, question_summary: questionSummary }),
    }).catch(() => {})
  }, [displayHistory])

  return {
    displayHistory, conversationId, sending, error, pastConversations, arrows, highlights,
    sendMessage, loadPastConversations, resumeConversation, sendFeedback,
  }
}

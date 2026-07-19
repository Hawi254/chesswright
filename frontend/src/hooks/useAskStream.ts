import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface AskCard {
  id: string
  question: string
  answer: string
  status: 'streaming' | 'settled' | 'error'
  errorMessage: string | null
  askedAt: string
}

export interface UseAskStreamResult {
  cards: AskCard[]
  ask: (question: string) => void
  retry: (cardId: string) => void
  clearHistory: () => void
}

const STORAGE_KEY = 'chesswright.ask.history'
const MAX_HISTORY = 20

function loadHistory(): AskCard[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// Only settled cards persist -- a resumed "streaming" card would be stuck
// mid-thought forever on reload, and a stale error shouldn't outlive the
// session that produced it (spec's Error handling section).
function saveHistory(cards: AskCard[]) {
  const settled = cards.filter((c) => c.status === 'settled').slice(0, MAX_HISTORY)
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settled))
  } catch {
    // Quota/private-mode failures are non-fatal -- history is a nice-to-have.
  }
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => null)
  return (body && typeof body.detail === 'string') ? body.detail : `status ${r.status}`
}

export function useAskStream(): UseAskStreamResult {
  const [cards, setCards] = useState<AskCard[]>(() => loadHistory())
  const controllersRef = useRef(new Map<string, AbortController>())

  useEffect(() => () => {
    controllersRef.current.forEach((controller) => controller.abort())
    controllersRef.current.clear()
  }, [])

  const runStream = useCallback((cardId: string, question: string) => {
    const controller = new AbortController()
    controllersRef.current.set(cardId, controller)

    const fail = (message: string) => {
      setCards((prev) => prev.map((c) => c.id === cardId
        ? { ...c, status: 'error' as const, errorMessage: message }
        : c))
    }

    fetch(`${API_BASE}/api/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await errorDetail(r))
        const reader = r.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) return
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split('\n\n')
          buffer = frames.pop() ?? ''
          for (const frame of frames) {
            const line = frame.trim()
            if (!line.startsWith('data:')) continue
            const parsed = JSON.parse(line.slice('data:'.length).trim()) as
              { delta?: string; done?: boolean; answer?: string; error?: string }
            if (parsed.error) {
              fail(parsed.error)
              return
            }
            if (parsed.done) {
              setCards((prev) => {
                const next = prev.map((c) => c.id === cardId
                  ? { ...c, status: 'settled' as const, answer: parsed.answer ?? c.answer }
                  : c)
                saveHistory(next)
                return next
              })
              return
            }
            if (typeof parsed.delta === 'string') {
              const delta = parsed.delta
              setCards((prev) => prev.map((c) => c.id === cardId
                ? { ...c, answer: c.answer + delta }
                : c))
            }
          }
        }
      })
      .catch((err: Error) => {
        if (controller.signal.aborted) return
        fail(err.message)
      })
      .finally(() => {
        controllersRef.current.delete(cardId)
      })
  }, [])

  const ask = useCallback((question: string) => {
    const id = crypto.randomUUID()
    setCards((prev) => [
      { id, question, answer: '', status: 'streaming', errorMessage: null, askedAt: new Date().toISOString() },
      ...prev,
    ])
    runStream(id, question)
  }, [runStream])

  const retry = useCallback((cardId: string) => {
    const target = cards.find((c) => c.id === cardId)
    if (!target) return
    setCards((prev) => prev.map((c) => c.id === cardId
      ? { ...c, status: 'streaming' as const, answer: '', errorMessage: null }
      : c))
    runStream(cardId, target.question)
  }, [cards, runStream])

  const clearHistory = useCallback(() => {
    controllersRef.current.forEach((controller) => controller.abort())
    controllersRef.current.clear()
    setCards([])
    saveHistory([])
  }, [])

  return { cards, ask, retry, clearHistory }
}

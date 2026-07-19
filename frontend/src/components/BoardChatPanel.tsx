import { useEffect, useState } from 'react'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'
import { useProStatus } from '../hooks/useProStatus'
import type { BoardChatDisplayEntry, BoardChatPastConversation } from '../hooks/useBoardChat'

export interface BoardChatPanelProps {
  gameId: string
  currentFen: string
  displayHistory: BoardChatDisplayEntry[]
  conversationId: number | null
  sending: boolean
  error: string | null
  pastConversations: BoardChatPastConversation[]
  sendMessage: (question: string, currentFen: string) => void
  loadPastConversations: () => void
  resumeConversation: (conversationId: number, currentFen: string) => void
  sendFeedback: (turnId: number, feedback: 1 | -1) => void
}

function ProUpsell() {
  return (
    <p className="mt-2 text-xs text-[var(--cw-text)]">
      <strong>Board Chat</strong> is a Chesswright Pro feature — ask Claude about
      this exact position, with arrows and highlights drawn on the board as it
      answers. Upgrade at{' '}
      <a
        href="https://chesswright.gumroad.com"
        target="_blank"
        rel="noreferrer"
        className="text-[var(--cw-copper)]"
      >
        chesswright.gumroad.com
      </a>
      .
    </p>
  )
}

export default function BoardChatPanel({
  gameId: _gameId,
  currentFen,
  displayHistory,
  conversationId,
  sending,
  error,
  pastConversations,
  sendMessage,
  loadPastConversations,
  resumeConversation,
  sendFeedback,
}: BoardChatPanelProps) {
  const proStatus = useProStatus()
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()
  const [question, setQuestion] = useState('')

  useEffect(() => {
    if (proStatus.active && claudeKeyAvailable) {
      loadPastConversations()
    }
    // loadPastConversations/gameId intentionally excluded: gameId is stable
    // per page mount and loadPastConversations is a stable useCallback from
    // the owning useBoardChat instance -- re-running only on gate flips.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proStatus.active, claudeKeyAvailable])

  function handleSend() {
    const trimmed = question.trim()
    if (!trimmed || sending) return
    sendMessage(trimmed, currentFen)
    setQuestion('')
  }

  const showPastConversations = conversationId === null && displayHistory.length === 0
    && pastConversations.length > 0

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <p className="font-condensed text-xs uppercase text-[var(--cw-muted)]">Board Chat</p>
      <p className="mt-1 text-xs text-[var(--cw-muted)]">
        Ask Claude about this exact position — it can draw arrows and highlight
        squares on the board as it answers.
      </p>

      {proStatus.loading ? null : !proStatus.active ? (
        <ProUpsell />
      ) : !claudeKeyAvailable ? (
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          Add your own Anthropic API key on the Settings page to enable Board Chat.
        </p>
      ) : (
        <>
          {showPastConversations && (
            <details className="mt-2">
              <summary className="cursor-pointer font-condensed text-xs text-[var(--cw-text)]">
                {pastConversations.length} past conversation{pastConversations.length !== 1 ? 's' : ''} for this game
              </summary>
              <ul className="mt-2 flex flex-col gap-2">
                {pastConversations.map((conv) => (
                  <li key={conv.id} className="flex items-center justify-between gap-2">
                    <span className="font-condensed text-xs text-[var(--cw-text)]">
                      Started {conv.started_at} — {conv.turn_count} turn{conv.turn_count !== 1 ? 's' : ''}
                    </span>
                    <button
                      type="button"
                      onClick={() => resumeConversation(conv.id, currentFen)}
                      className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
                    >
                      Resume
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className="mt-2 flex flex-col gap-2">
            {displayHistory.map((entry, i) => (
              <div key={i} className="flex flex-col gap-1">
                <p className="font-condensed text-xs text-[var(--cw-text)]">
                  <em>{entry.role === 'user' ? 'You' : 'Claude'}:</em> {entry.content}
                </p>
                {entry.role === 'assistant' && entry.turnId !== null && (
                  <span className="flex gap-2">
                    <button
                      type="button"
                      aria-label="Thumbs up"
                      onClick={() => sendFeedback(entry.turnId as number, 1)}
                      className="rounded border border-[var(--cw-line)] px-1.5 py-0.5 text-xs"
                    >
                      👍
                    </button>
                    <button
                      type="button"
                      aria-label="Thumbs down"
                      onClick={() => sendFeedback(entry.turnId as number, -1)}
                      className="rounded border border-[var(--cw-line)] px-1.5 py-0.5 text-xs"
                    >
                      👎
                    </button>
                  </span>
                )}
              </div>
            ))}
          </div>

          <div className="mt-2 flex items-center gap-2">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What's the best move here?"
              className="flex-1 rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] p-2 font-condensed text-xs text-[var(--cw-text)]"
            />
            <button
              type="button"
              disabled={!question.trim() || sending}
              onClick={handleSend}
              className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
            >
              {sending ? 'Claude is thinking…' : 'Send'}
            </button>
          </div>

          {error && <p className="mt-2 text-xs text-negative">{error}</p>}
        </>
      )}
    </div>
  )
}

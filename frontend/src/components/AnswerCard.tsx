import ReactMarkdown from 'react-markdown'
import { Button } from './ui/button'
import type { AskCard } from '../hooks/useAskStream'

export interface AnswerCardProps {
  card: AskCard
  onRetry: (cardId: string) => void
}

function relativeTime(iso: string): string {
  const diffSec = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (diffSec < 60) return 'just now'
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  return `${Math.round(diffHour / 24)}d ago`
}

export default function AnswerCard({ card, onRetry }: AnswerCardProps) {
  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <div className="flex items-start justify-between gap-4">
        <h3 className="font-condensed text-sm text-[var(--cw-text)]">{card.question}</h3>
        <span className="shrink-0 text-[10px] text-[var(--cw-muted)]">{relativeTime(card.askedAt)}</span>
      </div>

      {card.status === 'streaming' && card.answer === '' && (
        <p className="mt-2 text-xs text-[var(--cw-muted)]">Thinking…</p>
      )}

      {card.answer !== '' && (
        <div className="mt-2 text-xs text-[var(--cw-text)]">
          <ReactMarkdown>{card.answer}</ReactMarkdown>
        </div>
      )}

      {card.status === 'error' && (
        <div className="mt-3">
          <p className="text-xs text-negative">{card.errorMessage}</p>
          <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => onRetry(card.id)}>
            Retry
          </Button>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import AnswerCard from '../components/AnswerCard'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { useAskStream } from '../hooks/useAskStream'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'
import { useHeadlineStats } from '../hooks/useHeadlineStats'

// Ported verbatim from dashboard/ask_view.py::_PRESET_QUESTIONS.
const PRESET_QUESTIONS: Array<{ label: string; question: string }> = [
  { label: 'Blunder timing', question: 'When do I blunder most — opening, middlegame, or endgame?' },
  { label: 'Openings to keep/drop', question: 'Which opening should I drop, and which should I play more?' },
  { label: 'Missed tactics', question: "What's the one tactical motif I keep missing that's costing me the most rating points?" },
  { label: 'Biggest lever', question: 'If I could fix just one habit, what would move my results the most?' },
  { label: "This week's practice", question: "What's a realistic, specific thing I should practice this week based on my last batch of games?" },
  { label: 'Thrown-away points', question: 'Where do I throw away winning positions, and why does it usually happen?' },
  { label: 'Clock vs. blunders', question: 'Do I lose more games to the clock or to blunders?' },
]

export default function AskPage() {
  const { stats, loading, error } = useHeadlineStats()
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()
  const { cards, ask, retry, clearHistory } = useAskStream()
  const [question, setQuestion] = useState('')

  const submit = (q: string) => {
    const trimmed = q.trim()
    if (!trimmed) return
    ask(trimmed)
    setQuestion('')
  }

  const analyzedGames = stats?.analyzed_games ?? null
  const canAsk = !loading && !error && analyzedGames !== null && analyzedGames > 0 && claudeKeyAvailable

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Ask about your games</h1>
      <p className="mt-2 max-w-2xl text-sm text-[var(--cw-muted)]">
        Ask a question in plain English and get an answer grounded in your analyzed games. Claude works from
        the same stats that drive the rest of this app — win rates, ACPL, openings, phase accuracy, toughest
        opponents, and missed tactical patterns.
      </p>

      {loading && <p className="mt-4 text-[var(--cw-muted)]">Loading…</p>}

      {!loading && error && (
        <p className="mt-4 text-negative">
          Couldn&apos;t load your stats. Confirm the Chesswright API server is running.
        </p>
      )}

      {!loading && !error && analyzedGames === 0 && (
        <p className="mt-4 text-[var(--cw-muted)]">
          Not enough data yet — 0 analyzed game(s). Ask will fill in as more games are analyzed.
        </p>
      )}

      {!loading && !error && analyzedGames !== null && analyzedGames > 0 && !claudeKeyAvailable && (
        <p className="mt-4 text-[var(--cw-muted)]">
          Add your own Anthropic API key on the Settings page to enable this feature.
        </p>
      )}

      {canAsk && (
        <>
          <div className="mt-6">
            <p className="text-xs text-[var(--cw-muted)]">Try a preset question:</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {PRESET_QUESTIONS.map((preset) => (
                <Button
                  key={preset.label}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => submit(preset.question)}
                >
                  {preset.label}
                </Button>
              ))}
            </div>

            <div className="mt-3 flex gap-2">
              <Input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') submit(question)
                }}
                placeholder="e.g. When do I blunder most — opening, middlegame, or endgame?"
                className="flex-1"
              />
              <Button type="button" disabled={!question.trim()} onClick={() => submit(question)}>
                Ask
              </Button>
            </div>
          </div>

          {cards.length === 0 && (
            <p className="mt-3 text-xs text-[var(--cw-muted)]">
              Each question is answered fresh from your stats — it won&apos;t remember earlier questions.
            </p>
          )}

          {cards.length > 0 && (
            <div className="mt-2 flex justify-end">
              <Button type="button" variant="ghost" size="sm" onClick={clearHistory}>
                Clear history
              </Button>
            </div>
          )}

          {cards.map((card) => (
            <AnswerCard key={card.id} card={card} onRetry={retry} />
          ))}
        </>
      )}
    </div>
  )
}

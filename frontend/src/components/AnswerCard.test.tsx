import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AnswerCard from './AnswerCard'
import type { AskCard } from '../hooks/useAskStream'

function makeCard(overrides: Partial<AskCard> = {}): AskCard {
  return {
    id: 'c1', question: 'When do I blunder most?', answer: '', status: 'streaming',
    errorMessage: null, askedAt: new Date().toISOString(), ...overrides,
  }
}

describe('AnswerCard', () => {
  it('always shows the question as a heading', () => {
    render(<AnswerCard card={makeCard()} onRetry={vi.fn()} />)
    expect(screen.getByText('When do I blunder most?')).toBeInTheDocument()
  })

  it('shows a thinking indicator before the first token arrives', () => {
    render(<AnswerCard card={makeCard()} onRetry={vi.fn()} />)
    expect(screen.getByText('Thinking…')).toBeInTheDocument()
  })

  it('renders streamed markdown text as it arrives, hiding the thinking indicator', () => {
    render(<AnswerCard card={makeCard({ answer: 'You blunder most in the **middlegame**.' })} onRetry={vi.fn()} />)
    expect(screen.queryByText('Thinking…')).not.toBeInTheDocument()
    expect(screen.getByText(/middlegame/)).toBeInTheDocument()
  })

  it('shows the error message and a Retry button in the error state', async () => {
    const onRetry = vi.fn()
    render(
      <AnswerCard
        card={makeCard({ status: 'error', errorMessage: 'Claude API call failed: rate limited' })}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByText('Claude API call failed: rate limited')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledWith('c1')
  })

  it('does not show a Retry button in the settled state', () => {
    render(<AnswerCard card={makeCard({ status: 'settled', answer: 'Answer text.' })} onRetry={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })
})

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DrillSession from './DrillSession'

const CARD = {
  id: 1, fen: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
  source: 'Missed Tactics', best_move_san: 'Nf3', context: 'vs opponent',
  ease_factor: 2.5, interval_days: 0, repetitions: 0, next_due: '2020-01-01',
  added_at: '2020-01-01', last_reviewed_at: null, actual_move_san: null,
}

function stub() {
  return vi.fn((url: string) => {
    if (url.includes('/due-cards')) return Promise.resolve({ ok: true, json: async () => [CARD] })
    if (url.includes('/rate')) return Promise.resolve({ ok: true, json: async () => ({ interval_days: 1 }) })
    if (url.includes('/skip')) return Promise.resolve({ ok: true, json: async () => ({}) })
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
}

describe('DrillSession', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows a Start session button at the queue home, sized to dueCount', () => {
    vi.stubGlobal('fetch', stub())
    render(<DrillSession dueCount={1} onSessionChange={() => {}} />)
    expect(screen.getByRole('button', { name: /Start session \(1 cards?\)/i })).toBeInTheDocument()
  })

  it('shows "nothing due" when dueCount is 0', () => {
    vi.stubGlobal('fetch', stub())
    render(<DrillSession dueCount={0} onSessionChange={() => {}} />)
    expect(screen.getByText(/Nothing due today/i)).toBeInTheDocument()
  })

  it('starts a session and shows the card counter', async () => {
    vi.stubGlobal('fetch', stub())
    render(<DrillSession dueCount={1} onSessionChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Start session/i }))
    await waitFor(() => expect(screen.getByText('Card 1 of 1')).toBeInTheDocument())
  })

  it('reveals rating buttons after clicking Show answer, and posts a rating', async () => {
    const onSessionChange = vi.fn()
    vi.stubGlobal('fetch', stub())
    render(<DrillSession dueCount={1} onSessionChange={onSessionChange} />)
    fireEvent.click(screen.getByRole('button', { name: /Start session/i }))
    await waitFor(() => expect(screen.getByText('Card 1 of 1')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Show answer' }))
    const goodButton = await screen.findByRole('button', { name: 'Good' })
    fireEvent.click(goodButton)
    await waitFor(() => expect(onSessionChange).toHaveBeenCalled())
  })
})

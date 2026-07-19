import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CareerHighlight from './CareerHighlight'

const GAME_WITH_BADGES = {
  game_id: 'abc123', opponent_name: 'TestOpponent', utc_date: '2026-01-01',
  outcome_for_player: 'win' as const, is_comeback: true, is_giant_killing: false,
  is_brilliant_find: true, is_blunder_fest: false, is_nail_biter: false,
}

const GAME_NO_BADGES = {
  game_id: 'def456', opponent_name: 'QuietOpponent', utc_date: '2026-02-02',
  outcome_for_player: 'loss' as const, is_comeback: false, is_giant_killing: false,
  is_brilliant_find: false, is_blunder_fest: false, is_nail_biter: false,
}

describe('CareerHighlight', () => {
  it('renders nothing for null games', () => {
    const { container } = render(<CareerHighlight games={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for an empty array', () => {
    const { container } = render(<CareerHighlight games={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one card per game with its own badges', () => {
    render(<CareerHighlight games={[GAME_WITH_BADGES, GAME_NO_BADGES]} />)

    expect(screen.getByText('vs. TestOpponent on 2026-01-01 (win)')).toBeInTheDocument()
    expect(screen.getByText('vs. QuietOpponent on 2026-02-02 (loss)')).toBeInTheDocument()
    expect(screen.getByText('Comeback')).toBeInTheDocument()
    expect(screen.getByText('Brilliant find')).toBeInTheDocument()
    expect(screen.queryByText('Giant-killing')).not.toBeInTheDocument()
  })

  it('shows the shared badge legend once when any game has a badge', () => {
    render(<CareerHighlight games={[GAME_WITH_BADGES, GAME_NO_BADGES]} />)
    expect(screen.getAllByText(/Comeback: won\/drew after being clearly lost\./).length).toBe(1)
  })

  it('shows no legend when no game in the list has any badge', () => {
    render(<CareerHighlight games={[GAME_NO_BADGES]} />)
    expect(screen.queryByText(/Comeback: won\/drew/)).not.toBeInTheDocument()
  })

  it('renders no "View this game" affordance or any button', () => {
    render(<CareerHighlight games={[GAME_WITH_BADGES]} />)
    expect(screen.queryByText('View this game →')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders fewer than 3 cards when fewer than 3 games are given', () => {
    render(<CareerHighlight games={[GAME_WITH_BADGES]} />)
    expect(screen.getAllByText(/^vs\. /).length).toBe(1)
  })
})

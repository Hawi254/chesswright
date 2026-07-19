import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OpeningMoveTable from './OpeningMoveTable'
import type { OpeningMove } from '../hooks/useOpeningTreeMoves'

const MOVES: OpeningMove[] = [
  { san: 'e4', is_player_move: true, n_games: 10, n_wins: 6, n_draws: 2, n_losses: 2, win_pct: 60, draw_pct: 20, loss_pct: 20, avg_cpl: 15 },
]

describe('OpeningMoveTable', () => {
  it('shows the player-turn caption and Avg CPL column when playerTurn is true', () => {
    render(<OpeningMoveTable moves={MOVES} playerTurn onPlayMove={vi.fn()} />)
    expect(screen.getByText('Your moves from this position:')).toBeInTheDocument()
    expect(screen.getByText('Avg CPL')).toBeInTheDocument()
  })

  it('shows the opponent-turn caption and hides Avg CPL when playerTurn is false', () => {
    render(<OpeningMoveTable moves={MOVES} playerTurn={false} onPlayMove={vi.fn()} />)
    expect(screen.getByText('Opponent responses seen here:')).toBeInTheDocument()
    expect(screen.queryByText('Avg CPL')).not.toBeInTheDocument()
  })

  it('shows the explore-freely empty state when moves is empty and it is the player’s turn', () => {
    render(<OpeningMoveTable moves={[]} playerTurn onPlayMove={vi.fn()} />)
    expect(screen.getByText('No games recorded from this position — explore freely on the board.')).toBeInTheDocument()
  })

  it('shows the opponent empty state when moves is empty and it is not the player’s turn', () => {
    render(<OpeningMoveTable moves={[]} playerTurn={false} onPlayMove={vi.fn()} />)
    expect(screen.getByText('No opponent responses recorded here — play a move on the board to continue.')).toBeInTheDocument()
  })

  it('calls onPlayMove with the san when a row is clicked', () => {
    const onPlayMove = vi.fn()
    render(<OpeningMoveTable moves={MOVES} playerTurn onPlayMove={onPlayMove} />)
    fireEvent.click(screen.getByText('e4'))
    expect(onPlayMove).toHaveBeenCalledWith('e4')
  })

  it('renders an empty Avg CPL cell (not the string "None") when avg_cpl is null', () => {
    const movesWithNullCpl: OpeningMove[] = [{ ...MOVES[0], avg_cpl: null }]
    render(<OpeningMoveTable moves={movesWithNullCpl} playerTurn onPlayMove={vi.fn()} />)
    expect(screen.queryByText('None')).not.toBeInTheDocument()
  })
})

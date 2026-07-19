import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import GameExplorerTable from './GameExplorerTable'
import type { ExplorerGame } from '../hooks/useGameExplorer'

function game(overrides: Partial<ExplorerGame> = {}): ExplorerGame {
  return {
    game_id: 'abc123', utc_date: '2026-01-01', opponent_name: 'Foe', opponent_rating: 1500,
    player_color: 'white', outcome_for_player: 'win', time_control_category: 'blitz',
    opening_family: 'Sicilian Defense', rating_diff: 20, site: 'https://lichess.org/abc123',
    analysis_status: 'done', badge_count: 1, drama_score: 80, lichess_url: 'https://lichess.org/abc123',
    platform: 'Lichess', is_comeback: true, is_giant_killing: false, is_brilliant_find: false,
    is_blunder_fest: false, is_nail_biter: false,
    ...overrides,
  }
}

describe('GameExplorerTable', () => {
  it('renders nothing for an empty list', () => {
    const { container } = render(
      <GameExplorerTable games={[]} showPlatform={false} onSelectGame={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one row per game with headers', () => {
    render(
      <GameExplorerTable
        games={[game(), game({ game_id: 'def456', opponent_name: 'OtherFoe' })]}
        showPlatform={false}
        onSelectGame={vi.fn()}
      />,
    )
    expect(screen.getByText('Opponent')).toBeInTheDocument()
    expect(screen.getByText('Foe')).toBeInTheDocument()
    expect(screen.getByText('OtherFoe')).toBeInTheDocument()
    expect(screen.queryByText('Platform')).not.toBeInTheDocument()
  })

  it('shows the Platform column when showPlatform is true', () => {
    render(<GameExplorerTable games={[game()]} showPlatform={true} onSelectGame={vi.fn()} />)
    expect(screen.getByText('Platform')).toBeInTheDocument()
    expect(screen.getByText('Lichess')).toBeInTheDocument()
  })

  it('calls onSelectGame with the game_id when a row is clicked', () => {
    const onSelectGame = vi.fn()
    render(<GameExplorerTable games={[game()]} showPlatform={false} onSelectGame={onSelectGame} />)
    fireEvent.click(screen.getByText('Foe'))
    expect(onSelectGame).toHaveBeenCalledWith('abc123')
  })

  it('does not trigger row selection when the game link itself is clicked', () => {
    const onSelectGame = vi.fn()
    render(<GameExplorerTable games={[game()]} showPlatform={false} onSelectGame={onSelectGame} />)
    fireEvent.click(screen.getByText('View ↗'))
    expect(onSelectGame).not.toHaveBeenCalled()
  })

  it('renders badge chips for games that have them', () => {
    render(<GameExplorerTable games={[game()]} showPlatform={false} onSelectGame={vi.fn()} />)
    expect(screen.getByText('Comeback')).toBeInTheDocument()
    expect(screen.getByText(/Comeback: won\/drew after being clearly lost\./)).toBeInTheDocument()
  })

  it('omits the legend when no game has a badge', () => {
    render(
      <GameExplorerTable
        games={[game({ is_comeback: false })]}
        showPlatform={false}
        onSelectGame={vi.fn()}
      />,
    )
    expect(screen.queryByText(/Comeback: won\/drew/)).not.toBeInTheDocument()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GameExplorerPage from './GameExplorerPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const mockUseGameExplorer = vi.fn()
vi.mock('../hooks/useGameExplorer', () => ({
  useGameExplorer: () => mockUseGameExplorer(),
}))

function game(overrides = {}) {
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

function renderPage() {
  return render(
    <MemoryRouter>
      <GameExplorerPage />
    </MemoryRouter>,
  )
}

describe('GameExplorerPage', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
  })

  it('shows a loading state', () => {
    mockUseGameExplorer.mockReturnValue({ games: null, loading: true, error: false })
    renderPage()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows an error state', () => {
    mockUseGameExplorer.mockReturnValue({ games: null, loading: false, error: true })
    renderPage()
    expect(screen.getByText(/Couldn't load your games/)).toBeInTheDocument()
  })

  it('renders the game count and table once loaded', () => {
    mockUseGameExplorer.mockReturnValue({
      games: [game(), game({ game_id: 'def456', opponent_name: 'OtherFoe', is_comeback: false, badge_count: 0 })],
      loading: false, error: false,
    })
    renderPage()
    expect(screen.getByText(/2 games total \(1 with at least one badge\)/)).toBeInTheDocument()
    expect(screen.getByText('Foe')).toBeInTheDocument()
    expect(screen.getByText('OtherFoe')).toBeInTheDocument()
  })

  it('filters by opponent name search', () => {
    mockUseGameExplorer.mockReturnValue({
      games: [game(), game({ game_id: 'def456', opponent_name: 'OtherFoe' })],
      loading: false, error: false,
    })
    renderPage()
    fireEvent.change(screen.getByLabelText('Opponent name contains'), { target: { value: 'other' } })
    expect(screen.queryByText('Foe')).not.toBeInTheDocument()
    expect(screen.getByText('OtherFoe')).toBeInTheDocument()
  })

  it('filters by badge pill selection', () => {
    mockUseGameExplorer.mockReturnValue({
      games: [game(), game({ game_id: 'def456', opponent_name: 'OtherFoe', is_comeback: false })],
      loading: false, error: false,
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Comeback' }))
    expect(screen.getByText('Foe')).toBeInTheDocument()
    expect(screen.queryByText('OtherFoe')).not.toBeInTheDocument()
  })

  it('navigates to Game Detail when a row is selected', () => {
    mockUseGameExplorer.mockReturnValue({ games: [game()], loading: false, error: false })
    renderPage()
    fireEvent.click(screen.getByText('Foe'))
    expect(mockNavigate).toHaveBeenCalledWith('/game-explorer/abc123')
  })
})

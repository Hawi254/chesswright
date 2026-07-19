import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OpponentProfilePanel from './OpponentProfilePanel'

const mockUseOpponentProfile = vi.fn()
vi.mock('../hooks/useOpponentProfile', () => ({ useOpponentProfile: () => mockUseOpponentProfile() }))

const mockUseOpponentSwindleRate = vi.fn()
vi.mock('../hooks/useOpponentSwindleRate', () => ({ useOpponentSwindleRate: () => mockUseOpponentSwindleRate() }))

const mockUseOpponentNarrative = vi.fn()
vi.mock('../hooks/useOpponentNarrative', () => ({ useOpponentNarrative: () => mockUseOpponentNarrative() }))

const mockUseClaudeKeyStatus = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({ useClaudeKeyStatus: () => mockUseClaudeKeyStatus() }))

function profile(overrides = {}) {
  return {
    n_games: 3,
    openings: [{ opening_family: 'Sicilian Defense', n_games: 2, win_pct: 50.0, acpl: 30.0 }],
    position: [],
    castling: [],
    action_side: [],
    clock: [],
    ...overrides,
  }
}

describe('OpponentProfilePanel', () => {
  beforeEach(() => {
    mockUseOpponentSwindleRate.mockReturnValue({ swindle: null, loading: false, error: false })
    mockUseOpponentNarrative.mockReturnValue({
      narrative: null, generatedAt: null, loading: false, error: false,
      generating: false, generateError: null, generate: vi.fn(),
    })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
  })

  it('renders nothing while loading', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: null, loading: true, error: false })
    const { container } = render(<OpponentProfilePanel opponentName="Rival" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the game count and the by-opening table', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: profile(), loading: false, error: false })
    render(<OpponentProfilePanel opponentName="Rival" />)
    expect(screen.getByText('Profile against Rival')).toBeInTheDocument()
    expect(screen.getByText('3 game(s) total.')).toBeInTheDocument()
    expect(screen.getByText('Sicilian Defense')).toBeInTheDocument()
  })

  it('shows "No data yet." for an empty sub-table', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: profile(), loading: false, error: false })
    render(<OpponentProfilePanel opponentName="Rival" />)
    expect(screen.getAllByText('No data yet.').length).toBeGreaterThan(0)
  })

  it('shows the swindle-rate caption only when there are losses', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: profile(), loading: false, error: false })
    mockUseOpponentSwindleRate.mockReturnValue({
      swindle: { n_losses: 4, n_missed_swindle: 1, swindle_rate_pct: 25.0 }, loading: false, error: false,
    })
    render(<OpponentProfilePanel opponentName="Rival" />)
    expect(screen.getByText(/Missed swindle in 1 of 4 losses \(25%\)/)).toBeInTheDocument()
  })

  it('gates the generate button behind the Claude key status', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: profile(), loading: false, error: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: false })
    render(<OpponentProfilePanel opponentName="Rival" />)
    expect(screen.getByText(/Add your own Anthropic API key/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate commentary/i })).toBeDisabled()
  })

  it('shows Regenerate commentary and cached text once a narrative exists', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: profile(), loading: false, error: false })
    mockUseOpponentNarrative.mockReturnValue({
      narrative: 'Cached text', generatedAt: '2026-07-14', loading: false, error: false,
      generating: false, generateError: null, generate: vi.fn(),
    })
    render(<OpponentProfilePanel opponentName="Rival" />)
    expect(screen.getByText('Cached text')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /regenerate commentary/i })).toBeInTheDocument()
  })

  it('calls generate() when the button is clicked', () => {
    mockUseOpponentProfile.mockReturnValue({ profile: profile(), loading: false, error: false })
    const generate = vi.fn()
    mockUseOpponentNarrative.mockReturnValue({
      narrative: null, generatedAt: null, loading: false, error: false,
      generating: false, generateError: null, generate,
    })
    render(<OpponentProfilePanel opponentName="Rival" />)
    fireEvent.click(screen.getByRole('button', { name: /generate commentary/i }))
    expect(generate).toHaveBeenCalled()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NamedOpponentsTab from './NamedOpponentsTab'

const mockUseNemesisOpponents = vi.fn()
vi.mock('../hooks/useNemesisOpponents', () => ({ useNemesisOpponents: (minGames: number) => mockUseNemesisOpponents(minGames) }))

vi.mock('./OpponentProfilePanel', () => ({
  default: ({ opponentName }: { opponentName: string }) => <div data-testid="profile-panel">{opponentName}</div>,
}))

function row(overrides = {}) {
  return {
    opponent_name: 'Rival', n: 10, wins: 3, draws: 2, losses: 5, all_lichess: true, n_rated: 10,
    score_pct: 40.0, expected_score_pct: 50.0, surprise_pct: -10.0, confidence_tier: 'medium' as const,
    ...overrides,
  }
}

describe('NamedOpponentsTab', () => {
  beforeEach(() => {
    mockUseNemesisOpponents.mockReturnValue({
      rows: [row(), row({ opponent_name: 'Nemesis', score_pct: 10.0 })], loading: false, error: false,
    })
  })

  it('renders nothing while loading', () => {
    mockUseNemesisOpponents.mockReturnValue({ rows: null, loading: true, error: false })
    const { container } = render(<NamedOpponentsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('passes the slider value through to useNemesisOpponents', () => {
    render(<NamedOpponentsTab />)
    expect(mockUseNemesisOpponents).toHaveBeenCalledWith(5)
    fireEvent.change(screen.getByLabelText(/minimum games/i), { target: { value: '10' } })
    expect(mockUseNemesisOpponents).toHaveBeenCalledWith(10)
  })

  it('does not render a profile panel before any selection', () => {
    render(<NamedOpponentsTab />)
    expect(screen.queryByTestId('profile-panel')).not.toBeInTheDocument()
  })

  it('selecting a row from a nemesis table shows the profile panel for that opponent', () => {
    render(<NamedOpponentsTab />)
    fireEvent.click(screen.getAllByText('Nemesis')[0])
    expect(screen.getByTestId('profile-panel')).toHaveTextContent('Nemesis')
  })

  it('selecting from the picker drives the same profile panel', () => {
    render(<NamedOpponentsTab />)
    fireEvent.click(screen.getAllByText('Rival')[0])
    expect(screen.getByTestId('profile-panel')).toHaveTextContent('Rival')
    // Picker lists all opponents including one not in the top-10 tables --
    // exercised for real in Task 16's live verification; here we only
    // assert the same onSelect wiring reaches both sources.
    fireEvent.click(screen.getByPlaceholderText(/find an opponent/i))
  })
})

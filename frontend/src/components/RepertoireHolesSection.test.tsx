import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RepertoireHolesSection from './RepertoireHolesSection'

const mockUseRepertoireHoles = vi.fn()
vi.mock('../hooks/useRepertoireHoles', () => ({ useRepertoireHoles: () => mockUseRepertoireHoles() }))

vi.mock('./PositionInspector', () => ({
  default: (props: { fen: string | null; playerSan?: string }) => (
    <div data-testid="inspector" data-fen={props.fen ?? ''} data-player-san={props.playerSan ?? ''} />
  ),
}))

function hole(overrides = {}) {
  return {
    fen_before: 'fen1', n_games: 6, n_distinct_moves: 3, avg_cpl: 45.0,
    approx_move_number: 8, hole_score: 135.0, most_played_san: 'Nf3',
    opening: 'Sicilian Defense', ...overrides,
  }
}

describe('RepertoireHolesSection', () => {
  it('renders null while loading', () => {
    mockUseRepertoireHoles.mockReturnValue({ holes: null, loading: true, error: false })
    const { container } = render(<RepertoireHolesSection />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the "Biggest hole" caption from the first (highest hole_score) row', () => {
    mockUseRepertoireHoles.mockReturnValue({ holes: [hole()], loading: false, error: false })
    render(<RepertoireHolesSection />)
    expect(screen.getByText(/Biggest hole: move 8/)).toBeInTheDocument()
  })

  it('renders "--" for a null avg_cpl/hole_score row instead of crashing', () => {
    mockUseRepertoireHoles.mockReturnValue({
      holes: [hole({ avg_cpl: null, hole_score: null })], loading: false, error: false,
    })
    render(<RepertoireHolesSection />)
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
  })

  it('selecting a row feeds fen_before and most_played_san straight to PositionInspector', () => {
    mockUseRepertoireHoles.mockReturnValue({ holes: [hole()], loading: false, error: false })
    render(<RepertoireHolesSection />)
    fireEvent.click(screen.getByText('Nf3'))
    const inspector = screen.getByTestId('inspector')
    expect(inspector.dataset.fen).toBe('fen1')
    expect(inspector.dataset.playerSan).toBe('Nf3')
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PieceHandlingTab from './PieceHandlingTab'
import { usePatternsPieces } from '../hooks/usePatternsPieces'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsPieces')
const mockUsePatternsPieces = vi.mocked(usePatternsPieces)

const FULL_DATA = {
  piece_movement: [
    { piece: 'Q', piece_name: 'queen', n_moves: 10, acpl: 40, blunder_rate: 18 },
    { piece: 'R', piece_name: 'rook', n_moves: 10, acpl: 20, blunder_rate: 5 },
  ],
  piece_by_view: [
    { piece: 'Q', piece_name: 'queen', phase: 'opening', n_moves: 5, blunder_rate: 10 },
    { piece: 'R', piece_name: 'rook', phase: 'opening', n_moves: 5, blunder_rate: 4 },
  ],
  bishop_square_color: [
    { square_color: 'dark square', n_moves: 5, acpl: 30, blunder_rate: 5 },
    { square_color: 'light square', n_moves: 5, acpl: 32, blunder_rate: 6 },
  ],
  rook_king_backrank: [
    { piece: 'R', piece_name: 'rook', location: 'back rank', n_moves: 5, acpl: 20, blunder_rate: 5 },
    { piece: 'R', piece_name: 'rook', location: 'elsewhere', n_moves: 5, acpl: 45, blunder_rate: 12 },
  ],
  square_heatmap: {
    cells: [{ file: 'e', rank: 4, blunder_rate: 20, n_moves: 25 }],
    n_analyzed: 25,
    n_total_in_scope: 100,
  },
  motif_backfill_needed: true,
  castling: {
    win: [{ status: 'castled', n_games: 8, win_pct: 62.5 }, { status: 'did not castle', n_games: 2, win_pct: 50 }],
    acpl: [{ status: 'castled', n_games: 8, n_moves: 200, acpl: 30 }, { status: 'did not castle', n_games: 2, n_moves: 40, acpl: 55 }],
  },
}

describe('PieceHandlingTab', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders nothing while loading', () => {
    mockUsePatternsPieces.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<PieceHandlingTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsPieces.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<PieceHandlingTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders all 5 accordion panels, with panel 1 open by default', () => {
    mockUsePatternsPieces.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<PieceHandlingTab />)
    expect(screen.getByRole('button', { name: /Piece ACPL and blunder rate/ })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: /Piece handling by game phase/ })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /Bishop square color/ })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /Which squares see the most blunders/ })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /Castling and king safety/ })).toHaveAttribute('aria-expanded', 'false')
    // 2 (panel 1) + 1 (panel 2) + 2 (panel 3) + 1 (panel 4 heatmap) + 1 (panel 5) = 7
    expect(plotMock).toHaveBeenCalledTimes(7)
  })

  it('shows the motif backfill caption when motif_backfill_needed is true', () => {
    mockUsePatternsPieces.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<PieceHandlingTab />)
    expect(screen.getByText(/Missed-tactic classification/)).toBeInTheDocument()
  })

  it('shows a not-enough-data message instead of the heatmap when cells is empty', () => {
    mockUsePatternsPieces.mockReturnValue({
      data: { ...FULL_DATA, square_heatmap: { cells: [], n_analyzed: 3, n_total_in_scope: 100 } },
      loading: false, error: false,
    })
    render(<PieceHandlingTab />)
    expect(screen.getByText(/Not enough data yet \(3 of 100 moves analyzed\)/)).toBeInTheDocument()
    // 2 + 1 + 2 + 0 (heatmap panel falls back to text) + 1 = 6
    expect(plotMock).toHaveBeenCalledTimes(6)
  })

  it('calls usePatternsPieces with sharpness after clicking the view-sharpness toggle', () => {
    mockUsePatternsPieces.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<PieceHandlingTab />)
    expect(mockUsePatternsPieces).toHaveBeenLastCalledWith('phase')
    fireEvent.click(screen.getByRole('button', { name: 'View sharpness' }))
    expect(mockUsePatternsPieces).toHaveBeenLastCalledWith('sharpness')
  })
})

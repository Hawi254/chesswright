import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PositionsTab from './PositionsTab'
import { usePatternsPositions } from '../hooks/usePatternsPositions'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsPositions')
const mockUsePatternsPositions = vi.mocked(usePatternsPositions)

const FULL_DATA = {
  sharpness: [
    { bucket: 'flat (<5cp gap)', n_moves: 20, acpl: 5, blunder_rate: 1 },
    { bucket: 'forcing (200cp+)', n_moves: 20, acpl: 90, blunder_rate: 40 },
  ],
  material_structure: {
    rows: [
      { label: 'Queen', n_games: 5, win_pct: 60, draw_pct: 20, loss_pct: 20,
        acpl: 15, n_analyzed: 3 },
      { label: 'Rook', n_games: 5, win_pct: 40, draw_pct: 20, loss_pct: 40,
        acpl: null, n_analyzed: 0 },
    ],
    label_header: 'Category',
    n_unanalyzed: 1,
  },
  bishop_endings: [
    { bucket: 'same', n_moves: 25, acpl: 20 },
    { bucket: 'opposite', n_moves: 25, acpl: 100 },
  ],
  position_character: {
    bucket_win: [{ bucket: 'closed', n_games: 2, win_pct: 50 }],
    bucket_acpl: [{ bucket: 'closed', n_games: 1, n_moves: 1, acpl: 20, blunder_rate: 0 }],
    symmetric_win: [{ symmetry_label: 'symmetric', n_games: 1, win_pct: 100 }],
    symmetric_acpl: [{ symmetry_label: 'symmetric', n_games: 1, n_moves: 1, acpl: 20, blunder_rate: 0 }],
    central_tension_pct: 33.3,
    n_classified: 3,
    n_total_games: 3,
  },
  game_side: {
    castling_win: [{ castling_config: 'same-side', n_games: 1, win_pct: 100 }],
    castling_acpl: [{ castling_config: 'same-side', n_games: 1, n_moves: 1, acpl: 10, blunder_rate: 0 }],
    action_win: [{ action_side: 'balanced', n_games: 1, win_pct: 100 }],
    action_acpl: [{ action_side: 'balanced', n_games: 1, n_moves: 1, acpl: 10, blunder_rate: 0 }],
  },
}

describe('PositionsTab', () => {
  beforeEach(() => {
    plotMock.mockClear()
    mockUsePatternsPositions.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
  })

  it('renders nothing while loading', () => {
    mockUsePatternsPositions.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<PositionsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsPositions.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<PositionsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('starts with structure_type=endgame, grouped=false', () => {
    render(<PositionsTab />)
    expect(mockUsePatternsPositions).toHaveBeenLastCalledWith('endgame', false)
  })

  it('clicking Middlegame calls the hook with structureType=middlegame', () => {
    render(<PositionsTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Middlegame' }))
    expect(mockUsePatternsPositions).toHaveBeenLastCalledWith('middlegame', false)
  })

  it('checking the grouped checkbox calls the hook with grouped=true', () => {
    render(<PositionsTab />)
    fireEvent.click(screen.getByRole('checkbox'))
    expect(mockUsePatternsPositions).toHaveBeenLastCalledWith('endgame', true)
  })

  it('renders the material-structure table with the unified label column', () => {
    render(<PositionsTab />)
    expect(screen.getByText('Category')).toBeInTheDocument()
    expect(screen.getByText('Queen')).toBeInTheDocument()
    expect(screen.getByText('Rook')).toBeInTheDocument()
    expect(screen.getByText('--')).toBeInTheDocument()  // Rook's null acpl
    expect(screen.getByText(/ACPL is blank for 1 of 2 structures/)).toBeInTheDocument()
  })

  it('renders both bishop-ending tiles when 2+ buckets are present', () => {
    render(<PositionsTab />)
    // Scoped to each tile -- the material-structure table above also
    // renders "20.0" (Queen's draw_pct and loss_pct both happen to be 20),
    // so an unscoped getByText('20.0') is ambiguous across the page.
    const sameTile = screen.getByText('Same-color bishop endings ACPL').closest('div')!
    const oppositeTile = screen.getByText('Opposite-color bishop endings ACPL').closest('div')!
    expect(within(sameTile).getByText('20.0')).toBeInTheDocument()
    expect(within(oppositeTile).getByText('100.0')).toBeInTheDocument()
  })

  it('shows the not-enough-data fallback for bishop endings when fewer than 2 buckets', () => {
    mockUsePatternsPositions.mockReturnValue({
      data: { ...FULL_DATA, bishop_endings: [] }, loading: false, error: false,
    })
    render(<PositionsTab />)
    const fallbacks = screen.getAllByText('Not enough data yet.')
    expect(fallbacks.length).toBeGreaterThanOrEqual(1)
  })

  it('shows the not-enough-data fallback for panels 4-5 when n_classified is 0', () => {
    mockUsePatternsPositions.mockReturnValue({
      data: {
        ...FULL_DATA,
        position_character: { ...FULL_DATA.position_character, n_classified: 0,
                               bucket_win: [], bucket_acpl: [], symmetric_win: [], symmetric_acpl: [] },
      },
      loading: false, error: false,
    })
    render(<PositionsTab />)
    const fallbacks = screen.getAllByText('Not enough data yet.')
    expect(fallbacks.length).toBeGreaterThanOrEqual(2)
  })

  it('shows the not-enough-data fallback for panels 6-7 independently when game_side tables are empty', () => {
    mockUsePatternsPositions.mockReturnValue({
      data: {
        ...FULL_DATA,
        game_side: { castling_win: [], castling_acpl: [], action_win: [], action_acpl: [] },
      },
      loading: false, error: false,
    })
    render(<PositionsTab />)
    const fallbacks = screen.getAllByText('Not enough data yet.')
    expect(fallbacks.length).toBeGreaterThanOrEqual(2)
  })

  it('renders the central-tension caption only when central_tension_pct is not null', () => {
    render(<PositionsTab />)
    expect(screen.getByText(/33.3% still had/)).toBeInTheDocument()
  })
})

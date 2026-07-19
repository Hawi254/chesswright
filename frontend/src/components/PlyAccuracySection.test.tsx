import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlyAccuracySection from './PlyAccuracySection'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const mockUseOpeningsTable = vi.fn()
vi.mock('../hooks/useOpeningsTable', () => ({ useOpeningsTable: () => mockUseOpeningsTable() }))

const mockUseOpeningPlyAccuracy = vi.fn()
vi.mock('../hooks/useOpeningPlyAccuracy', () => ({ useOpeningPlyAccuracy: () => mockUseOpeningPlyAccuracy() }))

function opening(overrides = {}) {
  return { opening_family: 'Sicilian Defense', player_color: 'white', n: 42, win_pct: 55, draw_pct: 10, acpl: 32, n_analyzed: 20, ...overrides }
}

describe('PlyAccuracySection', () => {
  beforeEach(() => {
    mockUseOpeningsTable.mockReturnValue({
      openings: [opening(), opening({ opening_family: "Queen's Gambit", player_color: 'white' })],
      loading: false, error: false,
    })
    plotMock.mockClear()
  })

  it('renders null while the openings list is loading', () => {
    mockUseOpeningsTable.mockReturnValue({ openings: null, loading: true, error: false })
    mockUseOpeningPlyAccuracy.mockReturnValue({ rows: null, loading: false, error: false })
    const { container } = render(<PlyAccuracySection />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a single bar chart for the primary selection by default (no compare)', () => {
    mockUseOpeningPlyAccuracy.mockReturnValue({
      rows: [{ move_number: 1, n_games: 10, avg_cpl: 20, blunder_rate: 0 }], loading: false, error: false,
    })
    render(<PlyAccuracySection />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /compare against another opening/i })).toBeInTheDocument()
  })

  it('reveals the compare selector and two more charts when the toggle is clicked', () => {
    mockUseOpeningPlyAccuracy.mockReturnValue({
      rows: [{ move_number: 1, n_games: 10, avg_cpl: 20, blunder_rate: 0 }], loading: false, error: false,
    })
    render(<PlyAccuracySection />)
    fireEvent.click(screen.getByRole('button', { name: /compare against another opening/i }))
    expect(screen.getByLabelText(/compare against/i)).toBeInTheDocument()
  })

  it('shows the highest-CPL move-numbers caption from the top 3 rows', () => {
    mockUseOpeningPlyAccuracy.mockReturnValue({
      rows: [
        { move_number: 1, n_games: 10, avg_cpl: 20, blunder_rate: 0 },
        { move_number: 2, n_games: 10, avg_cpl: 50, blunder_rate: 10 },
      ],
      loading: false, error: false,
    })
    render(<PlyAccuracySection />)
    expect(screen.getByText(/Highest-CPL move numbers/)).toBeInTheDocument()
    expect(screen.getByText(/move 2/)).toBeInTheDocument()
  })
})

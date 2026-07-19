import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ComparisonsTab from './ComparisonsTab'
import { usePatternsComparisons } from '../hooks/usePatternsComparisons'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsComparisons')
const mockUsePatternsComparisons = vi.mocked(usePatternsComparisons)

const FULL_DATA = {
  favorite_underdog: {
    win: [
      { bucket: 'underdog', n_games: 3, win_pct: 66.7 },
      { bucket: 'even', n_games: 2, win_pct: 50 },
      { bucket: 'favorite', n_games: 3, win_pct: 33.3 },
    ],
    acpl: [
      { bucket: 'underdog', n_games: 2, n_moves: 40, acpl: 30 },
      { bucket: 'even', n_games: 2, n_moves: 40, acpl: 25 },
      { bucket: 'favorite', n_games: 2, n_moves: 40, acpl: 20 },
    ],
  },
  clock_pressure_by_rating_bucket: [
    { rating_bucket: 'underdog', time_bucket: 'critical (<5%)', n_moves: 20, acpl: 150, blunder_rate: 40 },
    { rating_bucket: 'favorite', time_bucket: 'critical (<5%)', n_moves: 20, acpl: 100, blunder_rate: 20 },
    { rating_bucket: 'even', time_bucket: 'critical (<5%)', n_moves: 20, acpl: 80, blunder_rate: 10 },
  ],
  openings_by_rating_bucket: [
    { rating_bucket: 'underdog', opening_family: 'Sicilian Defense', n_games: 5, win_pct: 60 },
    { rating_bucket: 'favorite', opening_family: 'Sicilian Defense', n_games: 5, win_pct: 40 },
    { rating_bucket: 'even', opening_family: 'Sicilian Defense', n_games: 5, win_pct: 50 },
  ],
  clock_pressure_by_outcome: [
    { outcome: 'win', time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 10, blunder_rate: 0 },
    { outcome: 'loss', time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 40, blunder_rate: 15 },
  ],
  clock_pressure_by_color: [
    { color: 'white', time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 15, blunder_rate: 5 },
    { color: 'black', time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 25, blunder_rate: 10 },
  ],
  clock_pressure_by_opening: [
    { opening_family: "Queen's Gambit", time_bucket: 'critical (<5%)', n_moves: 20, acpl: 150, blunder_rate: 40 },
    { opening_family: "Queen's Gambit", time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 50, blunder_rate: 5 },
  ],
}

describe('ComparisonsTab', () => {
  beforeEach(() => {
    plotMock.mockClear()
    mockUsePatternsComparisons.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
  })

  it('renders nothing while loading', () => {
    mockUsePatternsComparisons.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<ComparisonsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsComparisons.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<ComparisonsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a stat tile per bucket with win rate and ACPL', () => {
    render(<ComparisonsTab />)
    expect(screen.getByText('66.7%')).toBeInTheDocument()
    expect(screen.getByText('ACPL: 30.0')).toBeInTheDocument()
  })

  it('renders "no games" text in place of a tile for a bucket with zero rows', () => {
    mockUsePatternsComparisons.mockReturnValue({
      data: {
        ...FULL_DATA,
        favorite_underdog: {
          win: FULL_DATA.favorite_underdog.win.filter((r) => r.bucket !== 'favorite'),
          acpl: FULL_DATA.favorite_underdog.acpl.filter((r) => r.bucket !== 'favorite'),
        },
      },
      loading: false, error: false,
    })
    render(<ComparisonsTab />)
    expect(screen.getByText('Favorite: no games')).toBeInTheDocument()
  })

  it('shows the not-enough-data fallback when favorite_underdog.win is empty', () => {
    mockUsePatternsComparisons.mockReturnValue({
      data: { ...FULL_DATA, favorite_underdog: { win: [], acpl: [] } },
      loading: false, error: false,
    })
    render(<ComparisonsTab />)
    expect(screen.getAllByText('Not enough data yet.').length).toBeGreaterThanOrEqual(1)
  })

  it('shows the even-strength weighted-average caption', () => {
    render(<ComparisonsTab />)
    expect(screen.getByText(/Even-strength games: ACPL 80.0, blunder rate 10.0%/)).toBeInTheDocument()
  })

  it('renders the nested details reveal for the full three-bucket openings table', () => {
    render(<ComparisonsTab />)
    const details = screen.getByText('See all three buckets, including even-strength games')
    expect(details.closest('details')).toBeInTheDocument()
    // The table inside <details> is always in the DOM (native disclosure,
    // not conditionally rendered) -- all 3 rating_bucket values appear.
    expect(screen.getByText('even')).toBeInTheDocument()
  })

  it('shows the not-enough-data fallback for the openings panel when the underdog/favorite subset is empty', () => {
    mockUsePatternsComparisons.mockReturnValue({
      data: {
        ...FULL_DATA,
        openings_by_rating_bucket: FULL_DATA.openings_by_rating_bucket.filter(
          (r) => r.rating_bucket === 'even'),
      },
      loading: false, error: false,
    })
    render(<ComparisonsTab />)
    expect(screen.getAllByText('Not enough data yet.').length).toBeGreaterThanOrEqual(1)
  })

  it('restricts the critical-vs-plenty opening comparison to families present in both buckets', () => {
    mockUsePatternsComparisons.mockReturnValue({
      data: {
        ...FULL_DATA,
        clock_pressure_by_opening: [
          { opening_family: 'Only Critical', time_bucket: 'critical (<5%)', n_moves: 20, acpl: 150, blunder_rate: 40 },
          { opening_family: "Queen's Gambit", time_bucket: 'critical (<5%)', n_moves: 20, acpl: 150, blunder_rate: 40 },
          { opening_family: "Queen's Gambit", time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 50, blunder_rate: 5 },
        ],
      },
      loading: false, error: false,
    })
    render(<ComparisonsTab />)
    const openingsClockCall = plotMock.mock.calls.find((call) => {
      const props = call[0] as { data: Array<{ x: string[] }> }
      return props.data.some((trace) => trace.x?.includes("Queen's Gambit"))
        && !props.data.some((trace) => trace.x?.includes('Only Critical'))
    })
    expect(openingsClockCall).toBeDefined()
  })

  it('shows the not-enough-data fallback when critical/plenty share no common opening family', () => {
    mockUsePatternsComparisons.mockReturnValue({
      data: {
        ...FULL_DATA,
        clock_pressure_by_opening: [
          { opening_family: 'Only Critical', time_bucket: 'critical (<5%)', n_moves: 20, acpl: 150, blunder_rate: 40 },
          { opening_family: 'Only Plenty', time_bucket: 'plenty (60-100%)', n_moves: 20, acpl: 50, blunder_rate: 5 },
        ],
      },
      loading: false, error: false,
    })
    render(<ComparisonsTab />)
    expect(screen.getAllByText('Not enough data yet.').length).toBeGreaterThanOrEqual(1)
  })
})

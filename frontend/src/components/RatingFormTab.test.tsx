import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RatingFormTab from './RatingFormTab'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const mockUseMatchupsRatingForm = vi.fn()
vi.mock('../hooks/useMatchupsRatingForm', () => ({ useMatchupsRatingForm: () => mockUseMatchupsRatingForm() }))

function fullData(overrides = {}) {
  return {
    win_rate_by_rating_diff: [{ band: -100, n: 5, win_pct: 40.0 }],
    color_performance_by_rating: [
      { rating_bucket: 'underdog', black: null, white: null },
      { rating_bucket: 'even', black: 45.0, white: 50.0 },
      { rating_bucket: 'favorite', black: 60.0, white: 65.0 },
    ],
    giant_killing_counts: { n_upsets: 2, n_underdog_games: 4, n_collapses: 1, n_favorite_games: 3 },
    collapse_causes: {
      reason: [{ reason: 'hung_piece', n: 1, pct: 100.0 }],
      piece: [{ hung_piece: 'N', n: 1, pct: 100.0, piece_name: 'Knight' }],
      mate: [],
    },
    giant_killing_rate_trend: [
      { year: 2025, quarter: 1, period: '2025-Q1', label: 'Q1 2025', n_underdog: 4, n_upset: 2, pct_upset: 50.0, n_favorite: 3, n_collapse: 1, pct_collapse: 33.3 },
      { year: 2025, quarter: 2, period: '2025-Q2', label: 'Q2 2025', n_underdog: 2, n_upset: 0, pct_upset: 0.0, n_favorite: 1, n_collapse: 0, pct_collapse: 0.0 },
    ],
    comeback_collapse: { n_comebacks: 1, n_collapses: 1, comeback_game_ids: ['g1'], collapse_game_ids: ['g2'] },
    ...overrides,
  }
}

function renderTab() {
  return render(<MemoryRouter><RatingFormTab /></MemoryRouter>)
}

describe('RatingFormTab', () => {
  beforeEach(() => plotMock.mockClear())

  it('renders nothing while loading', () => {
    mockUseMatchupsRatingForm.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = renderTab()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the giant-killing count sentences', () => {
    mockUseMatchupsRatingForm.mockReturnValue({ data: fullData(), loading: false, error: false })
    renderTab()
    expect(screen.getByText('2 / 4')).toBeInTheDocument()
    expect(screen.getByText(/You win 50.0% of games as a heavy underdog/)).toBeInTheDocument()
    expect(screen.getByText(/You lose 33.3% of games as a heavy favorite/)).toBeInTheDocument()
  })

  it('renders "--" for a null color-performance cell', () => {
    mockUseMatchupsRatingForm.mockReturnValue({ data: fullData(), loading: false, error: false })
    renderTab()
    expect(screen.getAllByText('--').length).toBeGreaterThanOrEqual(2)
  })

  it('renders clickable comeback and collapse game lists', () => {
    mockUseMatchupsRatingForm.mockReturnValue({ data: fullData(), loading: false, error: false })
    renderTab()
    expect(screen.getByRole('link', { name: 'g1' })).toHaveAttribute('href', '/matchups/g1')
    expect(screen.getByRole('link', { name: 'g2' })).toHaveAttribute('href', '/matchups/g2')
  })

  it('shows a thin-data message instead of the trend chart when fewer than 2 quarters exist', () => {
    mockUseMatchupsRatingForm.mockReturnValue({
      data: fullData({ giant_killing_rate_trend: [] }), loading: false, error: false,
    })
    renderTab()
    const trendSection = screen.getByText('Giant-killing rate over time').closest('div') as HTMLElement
    expect(within(trendSection).getByText(/Not enough data yet/)).toBeInTheDocument()
  })
})

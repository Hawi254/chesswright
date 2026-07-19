import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RatingBenchmark from './RatingBenchmark'
import type { HeadlineTrend } from '../hooks/useInsightsData'
import type { HeadlineStats, RatingSnapshot } from '../hooks/useOverviewData'

const STATS_WITH_RATING: HeadlineStats = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000, implied_rating: 1973, rating_confidence: 'high',
}
const STATS_WITHOUT_RATING: HeadlineStats = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 10, implied_rating: null, rating_confidence: null,
}
const RATING_SNAPSHOT: RatingSnapshot = { current_rating: 1850, peak_rating: 1920 }
const TREND: HeadlineTrend = {
  compared_to_date: '2026-04-15',
  acpl_delta: -3.2, blunder_rate_delta: -0.8, win_pct_delta: 2.1, implied_rating_delta: 45,
}

describe('RatingBenchmark', () => {
  it('renders current vs. implied rating and a citation line when populated', () => {
    render(<RatingBenchmark stats={STATS_WITH_RATING} ratingSnapshot={RATING_SNAPSHOT} trend={null} />)
    expect(screen.getByTestId('rating-benchmark')).toBeInTheDocument()
    expect(screen.getByText('1850')).toBeInTheDocument()
    expect(screen.getByText('1973')).toBeInTheDocument()
    expect(screen.getByText(/45.2 ACPL/)).toBeInTheDocument()
    expect(screen.getByText(/Chess Digits/)).toBeInTheDocument()
  })

  it('renders a muted empty state when implied_rating is null', () => {
    render(<RatingBenchmark stats={STATS_WITHOUT_RATING} ratingSnapshot={RATING_SNAPSHOT} trend={null} />)
    expect(screen.getByTestId('rating-benchmark')).toBeInTheDocument()
    expect(screen.getByText(/not enough analyzed moves yet/i)).toBeInTheDocument()
    expect(screen.queryByText('1973')).not.toBeInTheDocument()
  })

  it('falls back to -- when current_rating is null', () => {
    render(
      <RatingBenchmark
        stats={STATS_WITH_RATING}
        ratingSnapshot={{ current_rating: null, peak_rating: null }}
        trend={null}
      />,
    )
    expect(screen.getByText('--')).toBeInTheDocument()
  })

  it('renders a TrendArrow next to implied rating when trend is populated', () => {
    render(<RatingBenchmark stats={STATS_WITH_RATING} ratingSnapshot={RATING_SNAPSHOT} trend={TREND} />)
    const arrow = screen.getByTestId('trend-arrow')
    expect(arrow).toHaveTextContent('▲45.0')
  })

  it('omits the TrendArrow when trend is null', () => {
    render(<RatingBenchmark stats={STATS_WITH_RATING} ratingSnapshot={RATING_SNAPSHOT} trend={null} />)
    expect(screen.queryByTestId('trend-arrow')).not.toBeInTheDocument()
  })
})

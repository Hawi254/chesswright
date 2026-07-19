import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PerformanceSummary from './PerformanceSummary'
import type { HeadlineTrend } from '../hooks/useInsightsData'
import type { Finding, HeadlineStats } from '../hooks/useOverviewData'

const STATS: HeadlineStats = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000, implied_rating: 1973, rating_confidence: 'high',
}

const FINDINGS: Finding[] = [
  { title: 'A', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'tactical' },
  { title: 'B', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'medium', category: 'time' },
  { title: 'C', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'defense' },
]

const TREND: HeadlineTrend = {
  compared_to_date: '2026-04-15',
  acpl_delta: -3.2, blunder_rate_delta: -0.8, win_pct_delta: 2.1, implied_rating_delta: 45,
}

describe('PerformanceSummary', () => {
  it('computes all 8 tiles from stats/findings client-side', () => {
    render(<PerformanceSummary stats={STATS} findings={FINDINGS} trend={null} />)
    expect(screen.getByText('40')).toBeInTheDocument() // Analyzed games
    expect(screen.getByText('40%')).toBeInTheDocument() // Coverage: 40/100
    expect(screen.getByText('45.2')).toBeInTheDocument() // ACPL
    expect(screen.getByText('5.1%')).toBeInTheDocument() // Blunder rate
    expect(screen.getByText('52.3%')).toBeInTheDocument() // Win %
    expect(screen.getByText('3')).toBeInTheDocument() // Insights generated
    expect(screen.getByText('1')).toBeInTheDocument() // Critical findings (severity high)
    expect(screen.getByText('2')).toBeInTheDocument() // Training opportunities (polarity weakness)
  })

  it('shows -- for coverage when total_games is 0', () => {
    render(<PerformanceSummary stats={{ ...STATS, total_games: 0, analyzed_games: 0 }} findings={[]} trend={null} />)
    expect(screen.getByText('--')).toBeInTheDocument()
  })

  it('renders a TrendArrow next to ACPL, blunder rate, and win % when trend is populated', () => {
    render(<PerformanceSummary stats={STATS} findings={FINDINGS} trend={TREND} />)
    expect(screen.getAllByTestId('trend-arrow')).toHaveLength(3)
  })

  it('shows the compared_to_date caption when trend is populated', () => {
    render(<PerformanceSummary stats={STATS} findings={FINDINGS} trend={TREND} />)
    expect(screen.getByText(/Trend vs\. 2026-04-15/)).toBeInTheDocument()
  })

  it('omits trend arrows and the caption entirely when trend is null', () => {
    render(<PerformanceSummary stats={STATS} findings={FINDINGS} trend={null} />)
    expect(screen.queryByTestId('trend-arrow')).not.toBeInTheDocument()
    expect(screen.queryByText(/Trend vs\./)).not.toBeInTheDocument()
  })
})

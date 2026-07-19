import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PointsMonthlyTrend from './PointsMonthlyTrend'
import type { PointsMonthlyRow } from '../hooks/usePointsLedger'

vi.mock('react-plotly.js', () => ({ default: () => <div data-testid="plot" /> }))

describe('PointsMonthlyTrend', () => {
  it('renders nothing with fewer than 2 months', () => {
    const rows: PointsMonthlyRow[] = [{ month: '2026-01-01', n_games: 5, actual_pct: 50, potential_pct: 80 }]
    const { container } = render(<PointsMonthlyTrend rows={rows} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the chart with 2+ months', () => {
    const rows: PointsMonthlyRow[] = [
      { month: '2026-01-01', n_games: 5, actual_pct: 50, potential_pct: 80 },
      { month: '2026-02-01', n_games: 6, actual_pct: 55, potential_pct: 82 },
    ]
    render(<PointsMonthlyTrend rows={rows} />)
    expect(screen.getByTestId('plot')).toBeInTheDocument()
  })
})

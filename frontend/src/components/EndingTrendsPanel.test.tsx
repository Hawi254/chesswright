import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EndingTrendsPanel from './EndingTrendsPanel'
import type { ResignationTrendRow, TimeForfeitTrendRow } from '../hooks/useEndingSummary'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const RESIGNATION: ResignationTrendRow[] = [
  { year: 2025, quarter: 1, period: 20251, label: '2025 Q1', n_total: 100, n_time_pressure: 10, pct: 10 },
  { year: 2025, quarter: 2, period: 20252, label: '2025 Q2', n_total: 120, n_time_pressure: 15, pct: 12.5 },
]
const TIME_FORFEIT: TimeForfeitTrendRow[] = [
  { year: 2025, quarter: 1, period: 20251, label: '2025 Q1', n_total: 50, n_ahead: 10, n_mutual: 5, pct_ahead: 20, pct_mutual: 10 },
  { year: 2025, quarter: 2, period: 20252, label: '2025 Q2', n_total: 60, n_ahead: 12, n_mutual: 6, pct_ahead: 20, pct_mutual: 10 },
]

describe('EndingTrendsPanel', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('shows the resignation trend by default', () => {
    render(<EndingTrendsPanel resignationTrend={RESIGNATION} timeForfeitTrend={TIME_FORFEIT} />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(plotMock.mock.calls[0][0].data[0].y).toEqual([10, 12.5])
  })

  it('switches to the time-forfeit two-line chart on toggle', async () => {
    render(<EndingTrendsPanel resignationTrend={RESIGNATION} timeForfeitTrend={TIME_FORFEIT} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Time forfeits: ahead vs. scrambling' }))
    expect(plotMock).toHaveBeenCalledTimes(2)
    const lastCall = plotMock.mock.calls[1][0]
    expect(lastCall.data).toHaveLength(2)
  })

  it('shows a muted message instead of a chart when a series has under 2 points', () => {
    render(<EndingTrendsPanel resignationTrend={[]} timeForfeitTrend={TIME_FORFEIT} />)
    expect(screen.getByText('Not enough games yet.')).toBeInTheDocument()
    expect(plotMock).not.toHaveBeenCalled()
  })
})

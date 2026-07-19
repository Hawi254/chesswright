import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TurningPointsTab from './TurningPointsTab'
import { usePatternsTurningPoints } from '../hooks/usePatternsTurningPoints'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsTurningPoints')
const mockUsePatternsTurningPoints = vi.mocked(usePatternsTurningPoints)

const FULL_DATA = {
  n_losses: 2,
  median_move: 14,
  most_common_phase: 'middlegame',
  by_move_bucket: [{ bucket: '6–10', n_losses: 1 }, { bucket: '21–25', n_losses: 1 }],
  by_phase: [{ phase: 'opening', n_losses: 1 }, { phase: 'middlegame', n_losses: 1 }],
  by_clock_bucket: [{ bucket: 'comfortable (30-60%)', n_losses: 1 }],
  n_no_clock_data: 1,
}

describe('TurningPointsTab', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders nothing while loading', () => {
    mockUsePatternsTurningPoints.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<TurningPointsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsTurningPoints.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<TurningPointsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a not-enough-data message when there are zero contested losses', () => {
    mockUsePatternsTurningPoints.mockReturnValue({
      data: { ...FULL_DATA, n_losses: 0, median_move: null, most_common_phase: null,
               by_move_bucket: [], by_phase: [], by_clock_bucket: [], n_no_clock_data: 0 },
      loading: false, error: false,
    })
    render(<TurningPointsTab />)
    expect(screen.getByText('Not enough data yet.')).toBeInTheDocument()
    expect(plotMock).not.toHaveBeenCalled()
  })

  it('renders the metric line, two 2-up charts, and the clock chart with real data', () => {
    mockUsePatternsTurningPoints.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<TurningPointsTab />)
    expect(screen.getByText('Typically move 14 (middlegame)')).toBeInTheDocument()
    expect(screen.getByText('Based on 2 losses with a contested position')).toBeInTheDocument()
    // move-number chart + phase chart + clock chart = 3
    expect(plotMock).toHaveBeenCalledTimes(3)
    expect(screen.getByText(/1 of 2 losses excluded from clock chart/)).toBeInTheDocument()
  })

  it('omits the clock chart and caption when by_clock_bucket is empty and n_no_clock_data is 0', () => {
    mockUsePatternsTurningPoints.mockReturnValue({
      data: { ...FULL_DATA, by_clock_bucket: [], n_no_clock_data: 0 },
      loading: false, error: false,
    })
    render(<TurningPointsTab />)
    // move-number chart + phase chart only = 2
    expect(plotMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByText(/excluded from clock chart/)).not.toBeInTheDocument()
  })
})

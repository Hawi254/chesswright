import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ClockTimeTab from './ClockTimeTab'
import { usePatternsClockTime } from '../hooks/usePatternsClockTime'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsClockTime')
const mockUsePatternsClockTime = vi.mocked(usePatternsClockTime)

const FULL_DATA = {
  blunder_rate_by_time_pressure: [{ bucket: 'critical (<5%)', n_moves: 10, acpl: 80, blunder_rate: 20 }],
  acpl_by_time_control: [{ time_control: 'blitz', n_games: 5, n_moves: 100, acpl: 40, blunder_rate: 5 }],
  thinking_time_blunder_correlation: [{ bucket: 'instant (<1s)', n_moves: 10, acpl: 60, blunder_rate: 15 }],
  instant_move_rate_by_phase: [{ bucket: 'opening (1-10)', n_moves: 20, n_instant: 4, instant_pct: 20 }],
  instant_move_accuracy: {
    rows: [{ bucket: 'forced-ish (≤3 legal replies)', n_moves: 5, acpl: 90, blunder_rate: 40 }],
    n_analyzed: 5,
    n_total_in_scope: 50,
  },
}

describe('ClockTimeTab', () => {
  // plotMock is module-scope (hoisted) and shared across every it() in this
  // file -- clear between tests so each assertion counts only its own
  // render, matching this repo's EvalGraph.test.tsx/PlyAccuracySection.test.tsx
  // convention.
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders nothing while loading', () => {
    mockUsePatternsClockTime.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<ClockTimeTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsClockTime.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<ClockTimeTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders all four accordion panels with a chart each', () => {
    mockUsePatternsClockTime.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<ClockTimeTab />)
    expect(screen.getByRole('button', { name: /Blunder rate vs\. time pressure/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ACPL by time control/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Blunder rate vs\. thinking time/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Instant moves/ })).toBeInTheDocument()
    // 5, not 4 -- the "Instant moves" panel bundles two distinct charts
    // (game-phase rate + accuracy-by-legal-replies) alongside the other
    // three panels' one chart each.
    expect(plotMock).toHaveBeenCalledTimes(5)
  })

  it('shows a not-enough-data message instead of a chart for empty instant-move data', () => {
    mockUsePatternsClockTime.mockReturnValue({
      data: {
        ...FULL_DATA,
        instant_move_rate_by_phase: [],
        instant_move_accuracy: { rows: [], n_analyzed: 0, n_total_in_scope: 0 },
      },
      loading: false,
      error: false,
    })
    render(<ClockTimeTab />)
    expect(screen.getAllByText('Not enough data yet.')).toHaveLength(2)
    // 3, not 2 -- the first three panels (time pressure, time control,
    // thinking time) always render their own chart regardless of the
    // instant-move data being empty; only the two instant-move charts fall
    // back to text.
    expect(plotMock).toHaveBeenCalledTimes(3)
  })
})

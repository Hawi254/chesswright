import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GameContextTab from './GameContextTab'
import { usePatternsGameContext } from '../hooks/usePatternsGameContext'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsGameContext')
const mockUsePatternsGameContext = vi.mocked(usePatternsGameContext)

const FULL_DATA = {
  phase_accuracy: [
    { phase: 'opening', n_games: 1, n_moves: 1, acpl: 10, blunder_rate: 0 },
    { phase: 'middlegame', n_games: 1, n_moves: 1, acpl: 200, blunder_rate: 100 },
  ],
  day_hour_heatmap: {
    cells: [
      { day: 'Mon', hour_local: 12, win_pct: 50, rating_diff_display: '+25' },
      { day: 'Tue', hour_local: 18, win_pct: 100, rating_diff_display: '+300' },
    ],
    utc_offset_hours: 0,
  },
}

describe('GameContextTab', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders nothing while loading', () => {
    mockUsePatternsGameContext.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<GameContextTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsGameContext.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<GameContextTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('always renders both panels -- no accordion, no collapse', () => {
    mockUsePatternsGameContext.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<GameContextTab />)
    // phase_accuracy bar chart + day/hour heatmap = 2
    expect(plotMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the rating-diff disclaimer caption above the heatmap', () => {
    mockUsePatternsGameContext.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<GameContextTab />)
    expect(screen.getByText(/average rating difference/)).toBeInTheDocument()
  })

  it('wires rating_diff_display through as the heatmap hoverExtra', () => {
    mockUsePatternsGameContext.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<GameContextTab />)
    const heatmapCall = plotMock.mock.calls.find(
      (call) => (call[0] as { data: Array<{ type: string }> }).data[0]?.type === 'heatmap',
    )
    expect(heatmapCall).toBeDefined()
    const heatmapProps = heatmapCall![0] as { data: Array<{ hovertemplate: string }> }
    expect(heatmapProps.data[0].hovertemplate).toContain('Avg rating diff')
  })

  it('includes the current UTC offset in the heatmap x-axis title', () => {
    mockUsePatternsGameContext.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
    render(<GameContextTab />)
    expect(screen.getByText(/UTC\+0/)).toBeInTheDocument()
  })
})

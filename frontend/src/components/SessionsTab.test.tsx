import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SessionsTab from './SessionsTab'
import { usePatternsSessions } from '../hooks/usePatternsSessions'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/usePatternsSessions')
const mockUsePatternsSessions = vi.mocked(usePatternsSessions)

const FULL_DATA = {
  session_rollup: [
    { session_start: '2026-01-01T10:00:00', session_end: '2026-01-01T10:05:00', n_games: 2,
      win_pct: 50, draw_pct: 0, loss_pct: 50, acpl: 10, n_analyzed: 1 },
    { session_start: '2026-01-02T09:00:00', session_end: '2026-01-02T09:00:00', n_games: 1,
      win_pct: 100, draw_pct: 0, loss_pct: 0, acpl: null, n_analyzed: 0 },
  ],
  prior_outcome: [
    { bucket: 'first_game_of_session', n_games: 1, n_moves: 20, acpl: 10, blunder_rate: 0 },
    { bucket: 'after a win', n_games: 1, n_moves: 20, acpl: 200, blunder_rate: 100 },
  ],
  session_position: [
    { position: 'game #1', n_games: 2, n_moves: 20, acpl: 10, blunder_rate: 0 },
    { position: 'game #2', n_games: 1, n_moves: 20, acpl: 200, blunder_rate: 100 },
  ],
  event_type: [
    { category: 'Casual', n_games: 2, win_pct: 50, draw_pct: 0, loss_pct: 50, acpl: 10, n_analyzed: 1 },
    { category: 'Tournament / Arena', n_games: 5, win_pct: 100, draw_pct: 0, loss_pct: 0, acpl: null, n_analyzed: 0 },
  ],
  event_name_breakdown: [
    { event: 'Weekly Rapid Arena', n_games: 5, win_pct: 100, draw_pct: 0, loss_pct: 0, acpl: 20, n_analyzed: 5 },
  ],
}

describe('SessionsTab', () => {
  beforeEach(() => {
    plotMock.mockClear()
    mockUsePatternsSessions.mockReturnValue({ data: FULL_DATA, loading: false, error: false })
  })

  it('renders nothing while loading', () => {
    mockUsePatternsSessions.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<SessionsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsSessions.mockReturnValue({ data: null, loading: false, error: true })
    const { container } = render(<SessionsTab />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the full-tab empty state and nothing else when session_rollup is empty', () => {
    mockUsePatternsSessions.mockReturnValue({
      data: { ...FULL_DATA, session_rollup: [] }, loading: false, error: false,
    })
    render(<SessionsTab />)
    expect(screen.getByText('Not enough data yet.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders the session summary stat tiles', () => {
    render(<SessionsTab />)
    // The Accordion keeps every panel's content mounted (CSS-collapsed, not
    // unmounted), so plain text queries collide with the "All sessions"
    // table's own game-count cells -- scope to the stat tile's own sibling.
    expect(screen.getByText('Total sessions').nextElementSibling).toHaveTextContent('2')
    expect(screen.getByText('Avg. games per session').nextElementSibling).toHaveTextContent('1.5')
    // weighted overall win %: (50*2 + 100*1) / 3 = 66.7
    expect(screen.getByText('Overall win rate').nextElementSibling).toHaveTextContent('66.7%')
  })

  it('caps win-rate-over-time and games-per-session to the most recent 60 sessions', () => {
    const manySessions = Array.from({ length: 65 }, (_, i) => ({
      session_start: `2026-01-${String(i + 1).padStart(2, '0')}T10:00:00`,
      session_end: `2026-01-${String(i + 1).padStart(2, '0')}T10:00:00`,
      n_games: 1, win_pct: 50, draw_pct: 0, loss_pct: 50, acpl: 10, n_analyzed: 1,
    }))
    mockUsePatternsSessions.mockReturnValue({
      data: { ...FULL_DATA, session_rollup: manySessions }, loading: false, error: false,
    })
    render(<SessionsTab />)
    expect(screen.getByText('Showing the most recent 60 of 65 sessions.')).toBeInTheDocument()
  })

  it('shows the not-enough-data fallback for the ACPL trend when every session has null acpl', () => {
    mockUsePatternsSessions.mockReturnValue({
      data: {
        ...FULL_DATA,
        session_rollup: FULL_DATA.session_rollup.map((r) => ({ ...r, acpl: null, n_analyzed: 0 })),
      },
      loading: false, error: false,
    })
    render(<SessionsTab />)
    expect(screen.getAllByText('Not enough data yet.').length).toBeGreaterThanOrEqual(1)
  })

  it('shows the ACPL coverage caption', () => {
    render(<SessionsTab />)
    expect(screen.getByText(/ACPL coverage: 1 of 2 sessions \(50.0%\)/)).toBeInTheDocument()
  })

  it('renders the All Sessions table with a "--" fallback for null acpl', () => {
    render(<SessionsTab />)
    // The event-type panel's own null-acpl tile also renders "--" -- scope
    // to the (first-rendered) All Sessions table specifically.
    const [allSessionsTable] = screen.getAllByRole('table')
    expect(within(allSessionsTable).getByText('--')).toBeInTheDocument()
  })

  it('shows the not-enough-data fallback for event type when empty', () => {
    mockUsePatternsSessions.mockReturnValue({
      data: { ...FULL_DATA, event_type: [] }, loading: false, error: false,
    })
    render(<SessionsTab />)
    expect(screen.getAllByText('Not enough data yet.').length).toBeGreaterThanOrEqual(1)
  })

  it('renders a per-category win-rate and ACPL tile for event type', () => {
    render(<SessionsTab />)
    expect(screen.getByText('Casual')).toBeInTheDocument()
    expect(screen.getByText('Tournament / Arena')).toBeInTheDocument()
  })

  it('shows the not-enough-data fallback for named tournaments when empty', () => {
    mockUsePatternsSessions.mockReturnValue({
      data: { ...FULL_DATA, event_name_breakdown: [] }, loading: false, error: false,
    })
    render(<SessionsTab />)
    expect(screen.getAllByText('Not enough data yet.').length).toBeGreaterThanOrEqual(1)
  })

  it('renders the named-tournaments table with a row-count caption', () => {
    render(<SessionsTab />)
    expect(screen.getByText('Weekly Rapid Arena')).toBeInTheDocument()
    expect(screen.getByText(/Showing 1 tournament/)).toBeInTheDocument()
  })
})

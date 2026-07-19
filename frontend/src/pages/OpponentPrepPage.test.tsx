import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OpponentPrepPage from './OpponentPrepPage'

const mockUseOpponentPrepStatus = vi.fn()
vi.mock('../hooks/useOpponentPrepStatus', () => ({
  useOpponentPrepStatus: () => mockUseOpponentPrepStatus(),
}))

const mockUseOpponentPrepReport = vi.fn()
const mockUseOpponentPrepOpponents = vi.fn()
vi.mock('../hooks/useOpponentPrepReport', () => ({
  useOpponentPrepReport: () => mockUseOpponentPrepReport(),
  useOpponentPrepOpponents: () => mockUseOpponentPrepOpponents(),
}))

vi.mock('../components/ScoutingNotesTab', () => ({ default: () => <div>Scouting Notes content</div> }))
vi.mock('../components/TournamentPrepTab', () => ({ default: () => <div>Tournament Prep content</div> }))

const IDLE_STATUS = { data: { status: 'idle', username: null, step: null, error: null }, loading: false, connectionLost: false }

describe('OpponentPrepPage', () => {
  it('shows previously-scouted suggestions when idle with no report loaded', () => {
    mockUseOpponentPrepStatus.mockReturnValue(IDLE_STATUS)
    mockUseOpponentPrepOpponents.mockReturnValue({ opponents: ['alice'], loading: false })
    mockUseOpponentPrepReport.mockReturnValue({ report: null, loading: false, error: false })

    render(<OpponentPrepPage />)
    expect(screen.getByRole('heading', { name: /Opponent Prep/i })).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
  })

  it('hides tabs and shows progress while a job is running', () => {
    mockUseOpponentPrepStatus.mockReturnValue({
      data: { status: 'running', username: 'DrNykterstein', step: 'analyzing', error: null },
      loading: false, connectionLost: false,
    })
    mockUseOpponentPrepOpponents.mockReturnValue({ opponents: [], loading: false })
    mockUseOpponentPrepReport.mockReturnValue({ report: null, loading: false, error: false })

    render(<OpponentPrepPage />)
    expect(screen.getByText(/Running Stockfish analysis/i)).toBeInTheDocument()
    expect(screen.queryByText('Repertoire')).not.toBeInTheDocument()
  })

  it('shows an error banner when the job failed', () => {
    mockUseOpponentPrepStatus.mockReturnValue({
      data: { status: 'error', username: 'DrNykterstein', step: null, error: 'Unknown user' },
      loading: false, connectionLost: false,
    })
    mockUseOpponentPrepOpponents.mockReturnValue({ opponents: [], loading: false })
    mockUseOpponentPrepReport.mockReturnValue({ report: null, loading: false, error: false })

    render(<OpponentPrepPage />)
    expect(screen.getByText(/Analysis failed: Unknown user/i)).toBeInTheDocument()
  })

  it('shows the thin-data warning under 5 games', () => {
    mockUseOpponentPrepStatus.mockReturnValue(IDLE_STATUS)
    mockUseOpponentPrepOpponents.mockReturnValue({ opponents: [], loading: false })
    mockUseOpponentPrepReport.mockReturnValue({
      report: {
        gamesAnalyzed: 3, colorSplit: { white: 2, black: 1 },
        dateRange: { from: '2026-01-01', to: '2026-02-01' }, repertoire: [],
      },
      loading: false, error: false,
    })

    render(<OpponentPrepPage />)
    expect(screen.getByText(/Not enough data yet/i)).toBeInTheDocument()
  })

  it('renders tabs once a report is loaded', () => {
    mockUseOpponentPrepStatus.mockReturnValue(IDLE_STATUS)
    mockUseOpponentPrepOpponents.mockReturnValue({ opponents: [], loading: false })
    mockUseOpponentPrepReport.mockReturnValue({
      report: {
        gamesAnalyzed: 12, colorSplit: { white: 7, black: 5 },
        dateRange: { from: '2026-01-01', to: '2026-06-01' },
        repertoire: [{ color: 'black', opening: 'Sicilian Defense', n_games: 5, score_pct: 40.0, avg_cpl: 55.0, blunder_pct: 12.0 }],
      },
      loading: false, error: false,
    })

    render(<OpponentPrepPage />)
    expect(screen.getByText('Repertoire')).toBeInTheDocument()
    expect(screen.getByText('Scouting Notes')).toBeInTheDocument()
    expect(screen.getByText('Tournament Prep Report')).toBeInTheDocument()
  })
})

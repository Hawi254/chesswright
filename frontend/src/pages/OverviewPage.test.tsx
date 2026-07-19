import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OverviewPage from './OverviewPage'
import type { OverviewData } from '../hooks/useOverviewData'

vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plot" />,
}))

const mockUseOverviewData = vi.fn()
vi.mock('../hooks/useOverviewData', () => ({
  useOverviewData: () => mockUseOverviewData(),
}))

const mockUseMilestones = vi.fn()
vi.mock('../hooks/useMilestones', () => ({
  useMilestones: () => mockUseMilestones(),
}))

const mockUseEvolutionData = vi.fn()
vi.mock('../hooks/useEvolutionData', () => ({
  useEvolutionData: () => mockUseEvolutionData(),
}))

const mockUseCareerHighlight = vi.fn()
vi.mock('../hooks/useCareerHighlight', () => ({
  useCareerHighlight: () => mockUseCareerHighlight(),
}))

const mockUseEngineStatus = vi.fn()
vi.mock('../hooks/useEngineStatus', () => ({
  useEngineStatus: () => mockUseEngineStatus(),
}))

const EMPTY: OverviewData = {
  stats: null, ratingSnapshot: null, streak: null, findings: null, narrative: null,
  loading: false, error: false,
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  )
}

describe('OverviewPage', () => {
  beforeEach(() => {
    mockUseMilestones.mockReturnValue({ milestones: null, loading: true, error: false })
    mockUseEvolutionData.mockReturnValue({
      ratingTrajectory: null, acplTrajectory: null, loading: true, error: false,
    })
    mockUseCareerHighlight.mockReturnValue({ games: null, loading: true, error: false })
    mockUseEngineStatus.mockReturnValue({
      connected: null, version: null, appVersion: null, loading: true, error: false,
    })
  })

  it('shows a loading indicator while loading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    renderPage()
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows an error message when loading fails', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    renderPage()
    expect(screen.getByText(/couldn.t load/i)).toBeInTheDocument()
  })

  it('renders the identity zone from sample data', () => {
    mockUseOverviewData.mockReturnValue({
      stats: { total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
               win_pct: 52.3, n_analyzed_moves: 4000 },
      ratingSnapshot: { current_rating: 1500, peak_rating: 1550 },
      streak: { outcome: 'win', length: 3 },
      findings: [
        { title: 'Sharp attacker', headline: 'h', detail: 'd', polarity: 'strength',
          severity: 'medium', category: 'tactical' },
        { title: 'Time trouble', headline: 'h', detail: 'd', polarity: 'weakness',
          severity: 'high', category: 'time' },
      ],
      narrative: 'You have played 100 games.',
      loading: false,
      error: false,
    })
    renderPage()

    const identityZone = screen.getByTestId('identity-zone')
    expect(within(identityZone).getByText('Sharp attacker')).toBeInTheDocument()
    expect(within(identityZone).getByText('Time trouble')).toBeInTheDocument()
    expect(screen.getByText('1500')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
  })

  it('renders milestones independently of identity-zone loading/error state', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    mockUseMilestones.mockReturnValue({
      milestones: [
        { achievement_id: 'first_win', name: 'First Win',
          description: 'Win your first recorded game.', unlocked_at: '2026-01-01T00:00:00' },
      ],
      loading: false,
      error: false,
    })
    renderPage()

    expect(screen.getByText('First Win')).toBeInTheDocument()
  })

  it('renders no milestones row while the milestones fetch is still loading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    mockUseMilestones.mockReturnValue({ milestones: null, loading: true, error: false })
    renderPage()

    expect(screen.queryByTestId('milestones-row')).not.toBeInTheDocument()
  })

  it('renders no milestones row when there are none unlocked', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    mockUseMilestones.mockReturnValue({ milestones: [], loading: false, error: false })
    renderPage()

    expect(screen.queryByTestId('milestones-row')).not.toBeInTheDocument()
  })

  it('renders the evolution block (shared zone head + charts) independently of identity-zone state', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    mockUseEvolutionData.mockReturnValue({
      ratingTrajectory: [{ year: 2024, avg_rating: 1400, n_games: 10 }],
      acplTrajectory: [{ year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 }],
      loading: false,
      error: false,
    })
    renderPage()

    expect(screen.getByText('Progress & milestones')).toBeInTheDocument()
    expect(screen.getByText('Rating, accuracy & activity over time')).toBeInTheDocument()
  })

  it('renders no evolution block when nothing in it has resolved', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    renderPage()

    expect(screen.queryByText('Progress & milestones')).not.toBeInTheDocument()
  })

  it('renders career highlight cards inside the evolution block even without rating data', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    mockUseCareerHighlight.mockReturnValue({
      games: [{
        game_id: 'abc', opponent_name: 'TestOpponent', utc_date: '2026-01-01',
        outcome_for_player: 'win', is_comeback: true, is_giant_killing: false,
        is_brilliant_find: false, is_blunder_fest: false, is_nail_biter: false,
      }],
      loading: false,
      error: false,
    })
    renderPage()

    expect(screen.getByText('vs. TestOpponent on 2026-01-01 (win)')).toBeInTheDocument()
    expect(screen.getByText('Progress & milestones')).toBeInTheDocument()
  })

  it('renders the coaching zone once findings resolve, even if other identity-zone fields are still missing', () => {
    mockUseOverviewData.mockReturnValue({
      stats: null,
      ratingSnapshot: null,
      streak: null,
      findings: [
        { title: 'Only weakness', headline: 'h', detail: 'd', polarity: 'weakness',
          severity: 'low', category: 'general' },
      ],
      narrative: null,
      loading: false,
      error: false,
    })
    renderPage()

    expect(screen.getByText('Your coaching plan')).toBeInTheDocument()
    expect(screen.getByText('Get your coaching plan →')).toBeInTheDocument()
  })

  it('renders no coaching zone while the overview fetch has not resolved', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    renderPage()

    expect(screen.queryByText('Your coaching plan')).not.toBeInTheDocument()
  })

  it('renders the engine-status strip once it and headline stats both resolve', () => {
    mockUseOverviewData.mockReturnValue({
      ...EMPTY, loading: false, error: false,
      stats: { total_games: 32295, analyzed_games: 4102, acpl: 38.1, blunder_rate: 5,
               win_pct: 54.2, n_analyzed_moves: 1000 },
    })
    mockUseEngineStatus.mockReturnValue({
      connected: false, version: null, appVersion: '0.1.25', loading: false, error: false,
    })
    renderPage()

    expect(
      screen.getByText('Chesswright v0.1.25 · 32,295 games · 4,102 analyzed · Engine not detected'),
    ).toBeInTheDocument()
  })
})

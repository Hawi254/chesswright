import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OverviewPage from './OverviewPage'
import type { OverviewData } from '../hooks/useOverviewData'

const mockUseOverviewData = vi.fn()
vi.mock('../hooks/useOverviewData', () => ({
  useOverviewData: () => mockUseOverviewData(),
}))

const mockUseMilestones = vi.fn()
vi.mock('../hooks/useMilestones', () => ({
  useMilestones: () => mockUseMilestones(),
}))

const EMPTY: OverviewData = {
  stats: null, ratingSnapshot: null, streak: null, findings: null, narrative: null,
  loading: false, error: false,
}

describe('OverviewPage', () => {
  beforeEach(() => {
    // Default: milestones still loading, so existing tests that don't care
    // about the milestones row see no unexpected content.
    mockUseMilestones.mockReturnValue({ milestones: null, loading: true, error: false })
  })

  it('always renders the Overview heading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    render(<OverviewPage />)
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  })

  it('shows a loading indicator while loading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    render(<OverviewPage />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows an error message when loading fails', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    render(<OverviewPage />)
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
    render(<OverviewPage />)

    expect(screen.getByText('Sharp attacker')).toBeInTheDocument()
    expect(screen.getByText('Time trouble')).toBeInTheDocument()
    expect(screen.getByText('1500')).toBeInTheDocument()
    expect(screen.getByText('peak 1550')).toBeInTheDocument()
    expect(screen.getByText(/3-game win streak/)).toBeInTheDocument()
    expect(screen.getByText('You have played 100 games.')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('52.3%')).toBeInTheDocument()
    expect(screen.getByText('45.2')).toBeInTheDocument()
  })

  it('caps trait tags at 3 and prioritizes strengths', () => {
    mockUseOverviewData.mockReturnValue({
      stats: { total_games: 10, analyzed_games: 10, acpl: 40, blunder_rate: 4,
               win_pct: 50, n_analyzed_moves: 100 },
      ratingSnapshot: { current_rating: 1400, peak_rating: 1400 },
      streak: { outcome: null, length: 0 },
      findings: [
        { title: 'Strength A', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'general' },
        { title: 'Strength B', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'general' },
        { title: 'Weakness A', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'general' },
        { title: 'Weakness B', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'general' },
      ],
      narrative: 'Narrative.',
      loading: false,
      error: false,
    })
    render(<OverviewPage />)

    expect(screen.getByText('Strength A')).toBeInTheDocument()
    expect(screen.getByText('Strength B')).toBeInTheDocument()
    expect(screen.getByText('Weakness A')).toBeInTheDocument()
    expect(screen.queryByText('Weakness B')).not.toBeInTheDocument()
    expect(screen.getByText('at peak')).toBeInTheDocument()
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
    render(<OverviewPage />)

    expect(screen.getByText('First Win')).toBeInTheDocument()
  })

  it('renders no milestones section while the milestones fetch is still loading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    mockUseMilestones.mockReturnValue({ milestones: null, loading: true, error: false })
    render(<OverviewPage />)

    expect(screen.queryByText('Milestones')).not.toBeInTheDocument()
  })

  it('renders no milestones section when there are none unlocked', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    mockUseMilestones.mockReturnValue({ milestones: [], loading: false, error: false })
    render(<OverviewPage />)

    expect(screen.queryByText('Milestones')).not.toBeInTheDocument()
  })
})

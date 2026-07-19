import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EvolutionPage from './EvolutionPage'
import { useEvolutionSummary } from '../hooks/useEvolutionSummary'

vi.mock('../hooks/useEvolutionSummary')
const mockUseEvolutionSummary = vi.mocked(useEvolutionSummary)

vi.mock('../components/CompositionChart', () => ({
  default: () => <div data-testid="composition-chart" />,
}))
vi.mock('../components/FamilyTimelineStrip', () => ({
  default: ({ row }: { row: { family: string } }) => <div data-testid={`strip-${row.family}`} />,
}))

const SUMMARY = {
  totalGames: 40,
  nPeriods: 8,
  composition: {
    shares: [{ period: 8072, label: '2018 Q1', family: 'Sicilian Defense', n_games: 10, share: 100 }],
    top: ['Sicilian Defense'],
  },
  ledger: [{
    family: 'Sicilian Defense', status: 'stable' as const, n_games_total: 40,
    share_early: 50, share_late: 50, win_early: 40, win_late: 45, n_early: 20, n_late: 20,
    first_label: '2018 Q1', last_label: '2019 Q4', adopted_label: '2018 Q1', dropped_label: '2019 Q4',
  }],
  strips: [{ period: 8072, label: '2018 Q1', family: 'Sicilian Defense', n_games: 10, share: 100 }],
}

describe('EvolutionPage', () => {
  it('shows a loading message while fetching', () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: null, loading: true, error: false })
    render(<EvolutionPage />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows an error message when the request fails', () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: null, loading: false, error: true })
    render(<EvolutionPage />)
    expect(screen.getByText(/Couldn't load your Repertoire Evolution data/)).toBeInTheDocument()
  })

  it('shows a no-games message when total_games is 0', () => {
    mockUseEvolutionSummary.mockReturnValue({
      summary: { ...SUMMARY, totalGames: 0, nPeriods: 0, ledger: [], strips: [], composition: { shares: [], top: [] } },
      loading: false, error: false,
    })
    render(<EvolutionPage />)
    expect(screen.getByText(/No games here yet/)).toBeInTheDocument()
  })

  it('shows a single-quarter message when nPeriods is below 2', () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: { ...SUMMARY, nPeriods: 1 }, loading: false, error: false })
    render(<EvolutionPage />)
    expect(screen.getByText(/fall in a single quarter/)).toBeInTheDocument()
  })

  it('renders the composition chart and one strip per ledger row when data is populated', () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: SUMMARY, loading: false, error: false })
    render(<EvolutionPage />)
    expect(screen.getByTestId('composition-chart')).toBeInTheDocument()
    expect(screen.getByTestId('strip-Sicilian Defense')).toBeInTheDocument()
  })

  it('shows a caption instead of strips when the ledger is empty but games exist', () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: { ...SUMMARY, ledger: [] }, loading: false, error: false })
    render(<EvolutionPage />)
    expect(screen.getByText(/No opening here clears the ledger's floors yet/)).toBeInTheDocument()
  })

  it('calls useEvolutionSummary with updated args after clicking the Black pill', () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: SUMMARY, loading: false, error: false })
    render(<EvolutionPage />)
    expect(mockUseEvolutionSummary).toHaveBeenLastCalledWith('white', null, 'family')
    fireEvent.click(screen.getByRole('button', { name: /Black/ }))
    expect(mockUseEvolutionSummary).toHaveBeenLastCalledWith('black', null, 'family')
  })

  it('calls useEvolutionSummary with the selected time control', async () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: SUMMARY, loading: false, error: false })
    render(<EvolutionPage />)
    fireEvent.change(screen.getByLabelText('Time control'), { target: { value: 'blitz' } })
    await waitFor(() => expect(mockUseEvolutionSummary).toHaveBeenLastCalledWith('white', 'blitz', 'family'))
  })

  it('calls useEvolutionSummary with eco grouping after switching the group-by select', async () => {
    mockUseEvolutionSummary.mockReturnValue({ summary: SUMMARY, loading: false, error: false })
    render(<EvolutionPage />)
    fireEvent.change(screen.getByLabelText('Group openings by'), { target: { value: 'eco' } })
    await waitFor(() => expect(mockUseEvolutionSummary).toHaveBeenLastCalledWith('white', null, 'eco'))
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FamilyTimelineStrip from './FamilyTimelineStrip'
import { useFamilyDeepDive } from '../hooks/useFamilyDeepDive'
import type { LedgerRow, StripPoint } from '../hooks/useEvolutionSummary'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

vi.mock('../hooks/useFamilyDeepDive')
const mockUseFamilyDeepDive = vi.mocked(useFamilyDeepDive)

const ROW: LedgerRow = {
  family: 'Sicilian Defense', status: 'rising', n_games_total: 40,
  share_early: 10, share_late: 30, win_early: 40, win_late: 60,
  n_early: 5, n_late: 15, first_label: '2018 Q1', last_label: '2025 Q4',
  adopted_label: '2018 Q1', dropped_label: '2025 Q4',
}

const STRIP_POINTS: StripPoint[] = [
  { period: 8072, label: '2018 Q1', family: 'Sicilian Defense', n_games: 2, share: 10 },
  { period: 8073, label: '2018 Q2', family: 'Sicilian Defense', n_games: 6, share: 30 },
]

describe('FamilyTimelineStrip', () => {
  beforeEach(() => {
    plotMock.mockClear()
    mockUseFamilyDeepDive.mockReturnValue({ deepDive: null, loading: false, error: false })
  })

  it('renders the family name, status badge with its date, and games count', () => {
    render(<FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    expect(screen.getByText('Sicilian Defense')).toBeInTheDocument()
    expect(screen.getByText('📈 Rising')).toBeInTheDocument()
    expect(screen.getByText('40 games')).toBeInTheDocument()
  })

  it('does not call useFamilyDeepDive with a real family until first expand', () => {
    render(<FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    expect(mockUseFamilyDeepDive).toHaveBeenLastCalledWith(null, 'white', null)
    fireEvent.click(screen.getByRole('button'))
    expect(mockUseFamilyDeepDive).toHaveBeenLastCalledWith('Sicilian Defense', 'white', null)
  })

  it('toggles aria-expanded on click but keeps passing the real family after collapsing (no refetch)', () => {
    render(<FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
    expect(mockUseFamilyDeepDive).toHaveBeenLastCalledWith('Sicilian Defense', 'white', null)
  })

  it('scales each quarter cell opacity by that quarter share divided by this row\'s own max share', () => {
    const { container } = render(
      <FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />,
    )
    const cells = container.querySelectorAll('[title^="2018"]')
    expect(cells).toHaveLength(2)
    expect((cells[0] as HTMLElement).style.opacity).toBe(String(10 / 30))
    expect((cells[1] as HTMLElement).style.opacity).toBe('1')
  })

  it('renders win-rate and ACPL line charts once deep dive data loads', () => {
    mockUseFamilyDeepDive.mockReturnValue({
      deepDive: {
        trend: [{ period: 8072, label: '2018 Q1', n_games: 5, n_wins: 2, win_pct: 40 },
                { period: 8073, label: '2018 Q2', n_games: 6, n_wins: 4, win_pct: 66.7 }],
        acpl: [{ label: '2018 Q1', n_moves: 40, n_games: 5, acpl: 35, n_total_games: 5, coverage_pct: 100 },
               { label: '2018 Q2', n_moves: 40, n_games: 6, acpl: 30, n_total_games: 6, coverage_pct: 100 }],
      },
      loading: false, error: false,
    })
    render(<FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    fireEvent.click(screen.getByRole('button'))
    expect(plotMock).toHaveBeenCalledTimes(2)
  })

  it('shows not-enough-data captions instead of charts when fewer than 2 points', () => {
    mockUseFamilyDeepDive.mockReturnValue({ deepDive: { trend: [], acpl: [] }, loading: false, error: false })
    render(<FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText(/Not enough games per quarter/)).toBeInTheDocument()
    expect(screen.getByText(/Not enough analyzed moves/)).toBeInTheDocument()
  })

  it('shows the coverage-skew warning when ACPL coverage is uneven across quarters', () => {
    mockUseFamilyDeepDive.mockReturnValue({
      deepDive: {
        trend: [{ period: 8072, label: '2018 Q1', n_games: 5, n_wins: 2, win_pct: 40 },
                { period: 8073, label: '2018 Q2', n_games: 6, n_wins: 4, win_pct: 66.7 }],
        acpl: [{ label: '2018 Q1', n_moves: 40, n_games: 1, acpl: 35, n_total_games: 22, coverage_pct: 4.5 },
               { label: '2018 Q2', n_moves: 40, n_games: 24, acpl: 30, n_total_games: 30, coverage_pct: 80.0 }],
      },
      loading: false, error: false,
    })
    render(<FamilyTimelineStrip row={ROW} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText(/aren't equally analyzed/)).toBeInTheDocument()
  })

  it('renders a 0% share-delta (not a dash) for a null win_late, since share is always defined', () => {
    const droppedRow: LedgerRow = { ...ROW, status: 'dropped', win_late: null, share_late: 0 }
    render(<FamilyTimelineStrip row={droppedRow} stripPoints={STRIP_POINTS} familyColor="#3987e5" color="white" timeControl={null} />)
    expect(screen.getByText('10% → 0%')).toBeInTheDocument()
  })
})

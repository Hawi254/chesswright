import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import PointsPage from './PointsPage'

vi.mock('react-plotly.js', () => ({ default: () => <div data-testid="plot" /> }))

const usePointsLedgerMock = vi.fn()
vi.mock('../hooks/usePointsLedger', () => ({ usePointsLedger: (...args: unknown[]) => usePointsLedgerMock(...args) }))

const FULL_SUMMARY = {
  tc_options: ['blitz', 'bullet'],
  n_games: 3, actual_pct: 33.3, leaked_points: 1.95, ceiling_pct: 98.3,
  buckets: [{ bucket: 'failed_conversion', n_games: 1, leaked: 0.45 }],
  monthly: [
    { month: '2026-01-01', n_games: 2, actual_pct: 50, potential_pct: 80 },
    { month: '2026-02-01', n_games: 1, actual_pct: 40, potential_pct: 90 },
  ],
  conversion_breakdown: {
    adv_band: [{ adv_band: 'completely winning (90%+)', n_games: 1, leaked: 0.45 }],
    conv_phase: [{ conv_phase: 'opening', n_games: 1, leaked: 0.45 }],
    conv_clock: [{ conv_clock: 'no clock data', n_games: 1, leaked: 0.45 }],
  },
  causes: { reason: [{ reason: 'other', n: 1, pct: 100 }], piece: [], mate: [] },
  costliest_games: [
    { game_id: 'g1', utc_date: '2026.01.01', opponent_name: 'Foe', outcome_for_player: 'draw',
      bucket: 'failed_conversion', best_chance: 0.95, leaked: 0.45, url: null },
  ],
  analyzed_games: null,
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PointsPage />
    </MemoryRouter>,
  )
}

describe('PointsPage', () => {
  it('always renders the page title, even while loading', () => {
    usePointsLedgerMock.mockReturnValue({ summary: null, loading: true, error: false })
    renderPage()
    expect(screen.getByRole('heading', { name: 'Where Your Points Go' })).toBeInTheDocument()
  })

  it('shows the global thin-data message when the ledger has no analyzed games at all', () => {
    usePointsLedgerMock.mockReturnValue({
      summary: { ...FULL_SUMMARY, tc_options: [], n_games: 0, buckets: [], costliest_games: [], analyzed_games: 0 },
      loading: false, error: false,
    })
    renderPage()
    expect(screen.getByText(/not enough data yet/i)).toBeInTheDocument()
    expect(screen.queryByTestId('plot')).not.toBeInTheDocument()
  })

  it('shows the empty-time-control message when tc_options is non-empty but n_games is 0', () => {
    usePointsLedgerMock.mockReturnValue({
      summary: { ...FULL_SUMMARY, n_games: 0, buckets: [], costliest_games: [], analyzed_games: null },
      loading: false, error: false,
    })
    renderPage()
    expect(screen.getByText(/no analyzed games in this time control yet/i)).toBeInTheDocument()
  })

  it('shows the no-leaks success message and renders nothing else (mirrors the Streamlit early return) when buckets is empty but games exist', () => {
    usePointsLedgerMock.mockReturnValue({
      summary: { ...FULL_SUMMARY, n_games: 2, buckets: [], costliest_games: [] },
      loading: false, error: false,
    })
    renderPage()
    expect(screen.getByText(/no leaked points found/i)).toBeInTheDocument()
    expect(screen.queryByTestId('plot')).not.toBeInTheDocument()
    expect(screen.queryByText('Foe')).not.toBeInTheDocument()
    expect(screen.queryByText('How the ledger is scored')).not.toBeInTheDocument()
    // The numeric readout tiles are computed independently of the leak
    // buckets (mirrors Streamlit's metric row, which renders before its
    // own equivalent early return) and still show.
    expect(screen.getByText('Games in ledger')).toBeInTheDocument()
  })

  it('renders the hero zone, headline, and costliest table for a populated summary', () => {
    usePointsLedgerMock.mockReturnValue({ summary: FULL_SUMMARY, loading: false, error: false })
    renderPage()
    expect(screen.getByText('Games in ledger')).toBeInTheDocument()
    expect(screen.getAllByTestId('plot').length).toBeGreaterThan(0)
    expect(screen.getByText(/your biggest leak is/i)).toBeInTheDocument()
    expect(screen.getByText('Foe')).toBeInTheDocument()
  })

  it('changing the time-control tab re-invokes usePointsLedger with the new value', async () => {
    usePointsLedgerMock.mockReturnValue({ summary: FULL_SUMMARY, loading: false, error: false })
    renderPage()
    await userEvent.click(screen.getByRole('tab', { name: 'Bullet' }))
    expect(usePointsLedgerMock).toHaveBeenLastCalledWith('bullet')
  })
})

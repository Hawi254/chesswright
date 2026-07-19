import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PositionTimelinePanel from './PositionTimelinePanel'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({ default: (props: unknown) => { plotMock(props); return <div data-testid="plot" /> } }))

describe('PositionTimelinePanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders nothing collapsed until expanded, then fetches and shows the chart', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({
        summary: { split_year: 2025, before_san: 'Nc3', before_n: 5, before_total: 5, before_share: 100,
          before_win_pct: 60, before_cpl: 10, after_san: 'Nf3', after_n: 6, after_total: 6, after_share: 100,
          after_win_pct: 66.7, after_cpl: 8 },
        rows: [{ san: 'Nc3', year: 2024, is_player_move: true, n_games: 5, n_wins: 3, n_draws: 1, n_losses: 1, cpl_sum: 50, cpl_n: 5 }],
      }),
    })))
    render(<PositionTimelinePanel fen="fen1" color="w" />)
    expect(screen.queryByTestId('plot')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText(/how this position changed over time/i))

    expect(await screen.findByTestId('plot')).toBeInTheDocument()
    // "Nc3"/"Nf3" render inside separate <strong> tags -- getByText only
    // matches a single element's own text by default, so a regex spanning
    // both (/Nc3.*Nf3/) never matches any one node ("the text is broken up
    // by multiple elements", per RTL's own error hint). Check each move
    // individually instead.
    expect(screen.getByText('Nc3')).toBeInTheDocument()
    expect(screen.getByText('Nf3')).toBeInTheDocument()
  })

  it('shows an empty state when summary is null (single-year data)', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ summary: null, rows: [] }) })))
    render(<PositionTimelinePanel fen="fen1" color="w" />)
    fireEvent.click(screen.getByText(/how this position changed over time/i))
    expect(await screen.findByText(/not enough data across multiple years/i)).toBeInTheDocument()
  })

  it('renders nothing at all when fen is null', () => {
    render(<PositionTimelinePanel fen={null} color="w" />)
    expect(screen.queryByText(/how this position changed over time/i)).not.toBeInTheDocument()
  })
})

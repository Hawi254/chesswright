import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TacticalHighlightsPage from './TacticalHighlightsPage'
import type { HighlightMoment } from '../hooks/useTacticalHighlightsReel'

const useTacticalHighlightsReelMock = vi.fn()
vi.mock('../hooks/useTacticalHighlightsReel', () => ({
  useTacticalHighlightsReel: () => useTacticalHighlightsReelMock(),
}))

const mockFilter = vi.fn(() => <div data-testid="filter" />)
vi.mock('../components/HighlightCategoryFilter', () => ({
  default: (props: unknown) => mockFilter(props),
}))

const mockReel = vi.fn(() => <div data-testid="reel" />)
vi.mock('../components/HighlightReel', () => ({
  default: (props: unknown) => mockReel(props),
}))

function moment(overrides: Partial<HighlightMoment> = {}): HighlightMoment {
  return {
    game_id: 'g1', category: 'brilliant', move_number: 5, san: 'Rxf7',
    magnitude: 500, magnitude_label: 'Rook sacrifice', strength: 0.56,
    caption: 'caption', opponent_name: 'Rival', utc_date: '2026-01-01',
    outcome_for_player: 'win', player_color: 'white', fen: 'fen-1',
    lastmove_from: 'f7', lastmove_to: 'f3',
    ...overrides,
  }
}

const COUNTS = { brilliant: 1, puzzle_conversion: 0, best_move_streak: 0, blown_mate: 0, great_escape: 0 }

function renderPage() {
  return render(
    <MemoryRouter>
      <TacticalHighlightsPage />
    </MemoryRouter>,
  )
}

describe('TacticalHighlightsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing but a loading state while loading', () => {
    useTacticalHighlightsReelMock.mockReturnValue({ moments: null, counts: null, loading: true, error: false })
    renderPage()
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    expect(screen.queryByTestId('filter')).not.toBeInTheDocument()
  })

  it('renders the whole-page empty state with a CTA when there are zero moments', () => {
    useTacticalHighlightsReelMock.mockReturnValue({ moments: [], counts: COUNTS, loading: false, error: false })
    renderPage()
    expect(screen.getByText(/nothing to show yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /go to analysis jobs/i })).toHaveAttribute(
      'href', '/analysis-jobs')
    expect(screen.queryByTestId('filter')).not.toBeInTheDocument()
  })

  it('composes the filter and reel once moments are loaded', () => {
    useTacticalHighlightsReelMock.mockReturnValue({
      moments: [moment()], counts: COUNTS, loading: false, error: false,
    })
    renderPage()
    expect(screen.getByTestId('filter')).toBeInTheDocument()
    expect(screen.getByTestId('reel')).toBeInTheDocument()
  })

  it('passes the top-20-by-strength slice to HighlightReel when activeCategory is all', () => {
    const low = moment({ game_id: 'low', category: 'blown_mate', strength: 0.1 })
    const high = moment({ game_id: 'high', category: 'blown_mate', strength: 0.9 })
    useTacticalHighlightsReelMock.mockReturnValue({
      moments: [low, high], counts: COUNTS, loading: false, error: false,
    })
    renderPage()
    const reelProps = mockReel.mock.calls[0][0] as { moments: HighlightMoment[] }
    expect(reelProps.moments.map((m) => m.game_id)).toEqual(['high', 'low'])
  })

  it('filters to one category, sorted by magnitude, when a chip is selected', async () => {
    const user = userEvent.setup()
    const brilliantMoment = moment({ game_id: 'b1', category: 'brilliant', magnitude: 300 })
    const streakMoment = moment({ game_id: 's1', category: 'best_move_streak', magnitude: 5 })
    useTacticalHighlightsReelMock.mockReturnValue({
      moments: [brilliantMoment, streakMoment], counts: COUNTS, loading: false, error: false,
    })
    renderPage()
    const onSelect = mockFilter.mock.calls[0][0].onSelect as (c: string) => void
    act(() => onSelect('best_move_streak'))
    await screen.findByTestId('reel')
    const reelProps = mockReel.mock.calls[mockReel.mock.calls.length - 1][0] as { moments: HighlightMoment[] }
    expect(reelProps.moments.map((m) => m.game_id)).toEqual(['s1'])
  })

  it('resets activeIndex to 0 when the category changes', async () => {
    const m1 = moment({ game_id: 'g1', category: 'brilliant' })
    const m2 = moment({ game_id: 'g2', category: 'brilliant' })
    useTacticalHighlightsReelMock.mockReturnValue({
      moments: [m1, m2], counts: COUNTS, loading: false, error: false,
    })
    renderPage()
    const onIndexChange = mockReel.mock.calls[0][0].onIndexChange as (i: number) => void
    act(() => onIndexChange(1))
    await screen.findByTestId('reel')
    expect(mockReel.mock.calls[mockReel.mock.calls.length - 1][0].activeIndex).toBe(1)

    const onSelect = mockFilter.mock.calls[0][0].onSelect as (c: string) => void
    act(() => onSelect('brilliant'))
    await screen.findByTestId('reel')
    expect(mockReel.mock.calls[mockReel.mock.calls.length - 1][0].activeIndex).toBe(0)
  })
})

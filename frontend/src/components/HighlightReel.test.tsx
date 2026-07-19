import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import HighlightReel from './HighlightReel'
import type { HighlightMoment } from '../hooks/useTacticalHighlightsReel'

vi.mock('./Chessboard', () => ({
  default: (props: { fen?: string; arrows?: Array<{ from: string; to: string }> }) => (
    <div data-testid="chessboard" data-fen={props.fen} data-arrows={JSON.stringify(props.arrows ?? [])} />
  ),
}))

function moment(overrides: Partial<HighlightMoment> = {}): HighlightMoment {
  return {
    game_id: 'g1', category: 'brilliant', move_number: 5, san: 'Rxf7',
    magnitude: 500, magnitude_label: 'Rook sacrifice', strength: 0.56,
    caption: 'Sacrificed a rook on move 5 — it worked.',
    opponent_name: 'Rival', utc_date: '2026-01-01', outcome_for_player: 'win',
    player_color: 'white', fen: 'fen-1', lastmove_from: 'f7', lastmove_to: 'f3',
    ...overrides,
  }
}

function renderReel(moments: HighlightMoment[], activeIndex = 0, onIndexChange = vi.fn()) {
  return render(
    <MemoryRouter>
      <HighlightReel
        moments={moments}
        activeCategory="all"
        activeIndex={activeIndex}
        onIndexChange={onIndexChange}
      />
    </MemoryRouter>,
  )
}

describe('HighlightReel', () => {
  it('renders the caption, magnitude stat, opponent/date/outcome, and board arrow', () => {
    renderReel([moment()])
    expect(screen.getByText('Sacrificed a rook on move 5 — it worked.')).toBeInTheDocument()
    expect(screen.getByText('Rook sacrifice')).toBeInTheDocument()
    expect(screen.getByText(/Rival/)).toBeInTheDocument()
    expect(screen.getByText(/2026-01-01/)).toBeInTheDocument()
    const board = screen.getByTestId('chessboard')
    expect(board.dataset.fen).toBe('fen-1')
    expect(JSON.parse(board.dataset.arrows ?? '[]')).toEqual([{ from: 'f7', to: 'f3', color: expect.any(String) }])
  })

  it('shows a position indicator and clickable dots', () => {
    renderReel([moment({ game_id: 'g1' }), moment({ game_id: 'g2' }), moment({ game_id: 'g3' })], 1)
    expect(screen.getByText('2 / 3')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /go to moment/i })).toHaveLength(3)
  })

  it('calls onIndexChange when Next is clicked', async () => {
    const user = userEvent.setup()
    const onIndexChange = vi.fn()
    renderReel([moment({ game_id: 'g1' }), moment({ game_id: 'g2' })], 0, onIndexChange)
    await user.click(screen.getByRole('button', { name: /next/i }))
    expect(onIndexChange).toHaveBeenCalledWith(1)
  })

  it('calls onIndexChange when Prev is clicked', async () => {
    const user = userEvent.setup()
    const onIndexChange = vi.fn()
    renderReel([moment({ game_id: 'g1' }), moment({ game_id: 'g2' })], 1, onIndexChange)
    await user.click(screen.getByRole('button', { name: /prev/i }))
    expect(onIndexChange).toHaveBeenCalledWith(0)
  })

  it('navigates with left/right arrow keys', () => {
    const onIndexChange = vi.fn()
    renderReel([moment({ game_id: 'g1' }), moment({ game_id: 'g2' })], 0, onIndexChange)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    expect(onIndexChange).toHaveBeenCalledWith(1)
  })

  it('does not go past the last or before the first moment', async () => {
    const user = userEvent.setup()
    const onIndexChange = vi.fn()
    renderReel([moment()], 0, onIndexChange)
    await user.click(screen.getByRole('button', { name: /next/i }))
    await user.click(screen.getByRole('button', { name: /prev/i }))
    expect(onIndexChange).not.toHaveBeenCalled()
  })

  it('renders a drill-through link to the hidden game-detail route', () => {
    renderReel([moment({ game_id: 'g42' })])
    expect(screen.getByRole('link', { name: /view full game/i })).toHaveAttribute(
      'href', '/tactical-highlights/g42')
  })

  it('renders a neutral empty state for brilliant when the filtered list is empty', () => {
    render(
      <MemoryRouter>
        <HighlightReel moments={[]} activeCategory="brilliant" activeIndex={0} onIndexChange={vi.fn()} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/no brilliant sacrifices/i)).toBeInTheDocument()
  })

  it('renders a positive empty state for blown_mate when the filtered list is empty', () => {
    render(
      <MemoryRouter>
        <HighlightReel moments={[]} activeCategory="blown_mate" activeIndex={0} onIndexChange={vi.fn()} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/no forced mates were ever let slip/i)).toBeInTheDocument()
  })

  it('renders a positive empty state for great_escape when the filtered list is empty', () => {
    render(
      <MemoryRouter>
        <HighlightReel moments={[]} activeCategory="great_escape" activeIndex={0} onIndexChange={vi.fn()} />
      </MemoryRouter>,
    )
    expect(screen.getByText(/no must-escape moments/i)).toBeInTheDocument()
  })
})

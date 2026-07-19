import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SavedVariationsPanel from './SavedVariationsPanel'
import type { SavedVariation } from '../hooks/useSavedVariations'

const VARIATION: SavedVariation = {
  id: 'v1', game_id: 'game1', branch_ply: 2,
  branch_fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
  moves: ['g8f6', 'b1c3'], title: null,
  created_at: '2026-07-14T00:00:00', updated_at: '2026-07-14T00:00:00',
}

describe('SavedVariationsPanel', () => {
  it('renders nothing when variations is empty', () => {
    const { container } = render(
      <SavedVariationsPanel variations={[]} onLoad={vi.fn()} onDelete={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('falls back to "From move N" when title is null', () => {
    render(<SavedVariationsPanel variations={[VARIATION]} onLoad={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText(/From move 1/)).toBeInTheDocument()
    expect(screen.getByText(/2 moves, branching at move 1/)).toBeInTheDocument()
  })

  it('uses the server-provided title when present', () => {
    render(
      <SavedVariationsPanel
        variations={[{ ...VARIATION, title: 'My Line' }]}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText(/My Line/)).toBeInTheDocument()
  })

  it('calls onLoad with the full variation when Load is clicked', () => {
    const onLoad = vi.fn()
    render(<SavedVariationsPanel variations={[VARIATION]} onLoad={onLoad} onDelete={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Load' }))
    expect(onLoad).toHaveBeenCalledWith(VARIATION)
  })

  it('calls onDelete with the variation id when Delete is clicked', () => {
    const onDelete = vi.fn()
    render(<SavedVariationsPanel variations={[VARIATION]} onLoad={vi.fn()} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledWith('v1')
  })

  it('renders a PGN download link pointing at the export endpoint', () => {
    render(<SavedVariationsPanel variations={[VARIATION]} onLoad={vi.fn()} onDelete={vi.fn()} />)
    const link = screen.getByRole('link', { name: 'PGN ↓' })
    expect(link).toHaveAttribute('href', expect.stringContaining('/api/variations/v1/pgn'))
    expect(link).toHaveAttribute('download')
  })
})

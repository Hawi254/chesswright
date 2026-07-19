import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OpeningTreeFlipDrawer from './OpeningTreeFlipDrawer'
import type { OpeningChange } from '../hooks/useOpeningTreeChanges'

vi.mock('./Chessboard', () => ({ default: () => <div data-testid="board" /> }))

const CHANGE: OpeningChange = {
  ply: 3, zobrist_hash: '7', path: ['e4', 'e5', 'Nc3'], before_san: 'Nc3', before_share: 100,
  before_win_pct: 60, before_total: 5, after_san: 'Nf3', after_share: 100, after_win_pct: 66.7, after_total: 6,
}

describe('OpeningTreeFlipDrawer', () => {
  it('renders nothing when change is null', () => {
    render(<OpeningTreeFlipDrawer change={null} color="w" onClose={vi.fn()} onJumpToPath={vi.fn()} />)
    expect(screen.queryByTestId('board')).not.toBeInTheDocument()
  })

  it('shows old/new move and era win rates', () => {
    render(<OpeningTreeFlipDrawer change={CHANGE} color="w" onClose={vi.fn()} onJumpToPath={vi.fn()} />)
    expect(screen.getByText('Nc3')).toBeInTheDocument()
    expect(screen.getByText('Nf3')).toBeInTheDocument()
    expect(screen.getByText(/60%/)).toBeInTheDocument()
    expect(screen.getByText(/66.7%/)).toBeInTheDocument()
  })

  it('calls onJumpToPath and onClose when Jump is clicked', () => {
    const onJumpToPath = vi.fn()
    const onClose = vi.fn()
    render(<OpeningTreeFlipDrawer change={CHANGE} color="w" onClose={onClose} onJumpToPath={onJumpToPath} />)
    fireEvent.click(screen.getByText('Jump to this position'))
    expect(onJumpToPath).toHaveBeenCalledWith(['e4', 'e5', 'Nc3'])
    expect(onClose).toHaveBeenCalled()
  })

  it('disables the jump action for a transposition-only change', () => {
    render(<OpeningTreeFlipDrawer change={{ ...CHANGE, path: null }} color="w" onClose={vi.fn()} onJumpToPath={vi.fn()} />)
    expect(screen.getByText(/no single verified move order/i)).toBeInTheDocument()
    expect(screen.queryByText('Jump to this position')).not.toBeInTheDocument()
  })
})

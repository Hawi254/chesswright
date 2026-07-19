import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MoveList from './MoveList'
import type { GameDetailMove } from '../hooks/useGameDetail'

function move(ply: number, san: string): GameDetailMove {
  return {
    ply, san, is_player_move: ply % 2, classification: 'good', cpl: 0, sharpness: 0.1,
    is_brilliant_candidate: false, is_puzzle_trigger: false, fen_before: 'x', fen_after: 'y',
    win_prob_before: 0.5, win_prob_after: 0.5, motif: null,
  }
}

const MOVES = [move(1, 'e4'), move(2, 'e5'), move(3, 'Nf3'), move(4, 'Nc6')]

describe('MoveList', () => {
  it('shows a message when there are no moves', () => {
    render(<MoveList moves={[]} currentPly={null} onSelectPly={vi.fn()} />)
    expect(screen.getByText('No moves recorded for this game.')).toBeInTheDocument()
  })

  it('numbers white moves and leaves black moves unnumbered', () => {
    render(<MoveList moves={MOVES} currentPly={1} onSelectPly={vi.fn()} />)
    expect(screen.getByText('1. e4')).toBeInTheDocument()
    expect(screen.getByText('e5')).toBeInTheDocument()
    expect(screen.getByText('2. Nf3')).toBeInTheDocument()
    expect(screen.getByText('Nc6')).toBeInTheDocument()
  })

  it('calls onSelectPly with the clicked move\'s ply', () => {
    const onSelectPly = vi.fn()
    render(<MoveList moves={MOVES} currentPly={1} onSelectPly={onSelectPly} />)
    fireEvent.click(screen.getByText('2. Nf3'))
    expect(onSelectPly).toHaveBeenCalledWith(3)
  })

  it('highlights the current ply', () => {
    render(<MoveList moves={MOVES} currentPly={3} onSelectPly={vi.fn()} />)
    expect(screen.getByText('2. Nf3').className).toContain('text-[var(--cw-copper)]')
  })
})

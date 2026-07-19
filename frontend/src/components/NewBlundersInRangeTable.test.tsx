import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NewBlundersInRangeTable from './NewBlundersInRangeTable'
import type { BatchImpactBlunder } from '../hooks/useBatchImpact'

const BLUNDERS: BatchImpactBlunder[] = [
  { gameId: 'g1', ply: 12, san: 'Qxf7', cpl: 350, motif: 'fork' },
  { gameId: 'g2', ply: 40, san: 'Rxe8', cpl: 900, motif: null },
]

describe('NewBlundersInRangeTable', () => {
  it('renders nothing when blunders is empty', () => {
    const { container } = render(<NewBlundersInRangeTable blunders={[]} onSelectGame={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one row per blunder', () => {
    render(<NewBlundersInRangeTable blunders={BLUNDERS} onSelectGame={vi.fn()} />)
    expect(screen.getByText('Qxf7')).toBeInTheDocument()
    expect(screen.getByText('900')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()  // null motif
  })

  it('calls onSelectGame with the game id when a row is clicked', () => {
    const onSelectGame = vi.fn()
    render(<NewBlundersInRangeTable blunders={BLUNDERS} onSelectGame={onSelectGame} />)
    fireEvent.click(screen.getByText('Qxf7'))
    expect(onSelectGame).toHaveBeenCalledWith('g1')
  })
})

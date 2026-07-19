import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import PointsCostliestTable from './PointsCostliestTable'
import type { PointsCostliestGame } from '../hooks/usePointsLedger'

const GAMES: PointsCostliestGame[] = [
  { game_id: 'g1', utc_date: '2026.01.01', opponent_name: 'Foe', outcome_for_player: 'draw',
    bucket: 'failed_conversion', best_chance: 0.95, leaked: 0.45, url: 'https://lichess.org/g1' },
  { game_id: 'g2', utc_date: '2026.01.02', opponent_name: 'Rival', outcome_for_player: 'loss',
    bucket: 'failed_hold', best_chance: 0.5, leaked: 0.5, url: null },
]

describe('PointsCostliestTable', () => {
  it('renders nothing when there are no games', () => {
    const { container } = render(
      <PointsCostliestTable games={[]} activeBucket={null} onClearBucket={vi.fn()} onSelectGame={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one row per game with no filter chip when activeBucket is null', () => {
    render(<PointsCostliestTable games={GAMES} activeBucket={null} onClearBucket={vi.fn()} onSelectGame={vi.fn()} />)
    expect(screen.getByText('Foe')).toBeInTheDocument()
    expect(screen.getByText('Rival')).toBeInTheDocument()
    expect(screen.queryByText(/Showing:/)).not.toBeInTheDocument()
  })

  it('filters to the active bucket and shows a clearable chip', async () => {
    const onClearBucket = vi.fn()
    render(
      <PointsCostliestTable games={GAMES} activeBucket="failed_conversion" onClearBucket={onClearBucket} onSelectGame={vi.fn()} />,
    )
    expect(screen.getByText('Foe')).toBeInTheDocument()
    expect(screen.queryByText('Rival')).not.toBeInTheDocument()
    await userEvent.click(screen.getByText(/Showing: Failed conversion/))
    expect(onClearBucket).toHaveBeenCalled()
  })

  it('calls onSelectGame with the game_id when a row is clicked', async () => {
    const onSelectGame = vi.fn()
    render(<PointsCostliestTable games={GAMES} activeBucket={null} onClearBucket={vi.fn()} onSelectGame={onSelectGame} />)
    await userEvent.click(screen.getByText('Foe'))
    expect(onSelectGame).toHaveBeenCalledWith('g1')
  })

  it('renders no link for a game with a null url', () => {
    render(<PointsCostliestTable games={GAMES} activeBucket={null} onClearBucket={vi.fn()} onSelectGame={vi.fn()} />)
    expect(screen.getAllByText('View ↗')).toHaveLength(1)
  })
})

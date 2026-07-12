import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MilestonesRow from './MilestonesRow'

describe('MilestonesRow', () => {
  it('renders nothing for an empty array', () => {
    const { container } = render(<MilestonesRow milestones={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a chip per milestone with name and truncated date', () => {
    render(
      <MilestonesRow
        milestones={[
          { achievement_id: 'first_win', name: 'First Win',
            description: 'Win your first recorded game.', unlocked_at: '2026-01-01T00:00:00' },
          { achievement_id: 'century_club', name: 'Century Club',
            description: 'Play 100 games.', unlocked_at: '2026-02-15T12:30:00' },
        ]}
      />,
    )

    expect(screen.getByText('First Win')).toBeInTheDocument()
    expect(screen.getByText('2026-01-01')).toBeInTheDocument()
    expect(screen.getByText('Century Club')).toBeInTheDocument()
    expect(screen.getByText('2026-02-15')).toBeInTheDocument()
  })
})

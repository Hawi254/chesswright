import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RecentImprovements from './RecentImprovements'

const MILESTONES = [
  { achievement_id: 'first_win', name: 'First Win',
    description: 'Win your first recorded game.', unlocked_at: '2026-01-01T00:00:00' },
  { achievement_id: 'century_club', name: 'Century Club',
    description: 'Play 100 games.', unlocked_at: '2026-02-15T12:30:00' },
]

describe('RecentImprovements', () => {
  it('renders a ZoneHead title and one chip per milestone', () => {
    render(<RecentImprovements milestones={MILESTONES} />)

    expect(screen.getByText('Recent improvements')).toBeInTheDocument()
    expect(screen.getByText("What's unlocked lately")).toBeInTheDocument()
    expect(screen.getByText('First Win')).toBeInTheDocument()
    expect(screen.getByText('2026-01-01')).toBeInTheDocument()
    expect(screen.getByText('Century Club')).toBeInTheDocument()
    expect(screen.getByText('2026-02-15')).toBeInTheDocument()
  })

  it('renders the muted empty state when there are no milestones', () => {
    render(<RecentImprovements milestones={[]} />)

    expect(screen.getByText('Nothing unlocked yet — keep playing and analyzing.')).toBeInTheDocument()
    expect(screen.queryByText('First Win')).not.toBeInTheDocument()
  })
})

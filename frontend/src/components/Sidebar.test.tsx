import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Sidebar from './Sidebar'
import { STATIC_CANDIDATES } from '../lib/navCandidates'

vi.mock('../hooks/usePageCandidates', () => ({
  usePageCandidates: () => ({ candidates: STATIC_CANDIDATES, usingFallback: false }),
}))

describe('Sidebar', () => {
  it('renders all 3 groups with the correct page counts', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText('Career')).toBeInTheDocument()
    expect(screen.getByText('Explore')).toBeInTheDocument()
    expect(screen.getByText('App')).toBeInTheDocument()

    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Game Explorer')).toBeInTheDocument()
    expect(screen.getByText('Batch Impact')).toBeInTheDocument()

    // Settings-category candidates must never appear in the sidebar --
    // only the "Settings" page itself, not its 6 sub-sections.
    expect(screen.queryByText('Anthropic API key')).not.toBeInTheDocument()
  })
})

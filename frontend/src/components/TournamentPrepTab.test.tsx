import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TournamentPrepTab from './TournamentPrepTab'

const mockUseProStatus = vi.fn()
vi.mock('../hooks/useProStatus', () => ({ useProStatus: () => mockUseProStatus() }))

describe('TournamentPrepTab', () => {
  it('shows the Pro upsell when not licensed', () => {
    mockUseProStatus.mockReturnValue({ active: false, loading: false })
    render(<TournamentPrepTab username="DrNykterstein" />)
    expect(screen.getByText(/Chesswright Pro/i)).toBeInTheDocument()
  })

  it('shows nothing while pro status is loading', () => {
    mockUseProStatus.mockReturnValue({ active: false, loading: true })
    const { container } = render(<TournamentPrepTab username="DrNykterstein" />)
    expect(container.querySelector('[data-testid="tournament-prep-content"]')).toBeNull()
  })

  it('shows a generate button when licensed', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    render(<TournamentPrepTab username="DrNykterstein" />)
    expect(screen.getByText(/Generate/i)).toBeInTheDocument()
  })
})

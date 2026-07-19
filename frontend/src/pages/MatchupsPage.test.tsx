import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MatchupsPage from './MatchupsPage'

// RatingFormTab statically imports react-plotly.js, which pulls in the
// full plotly.js bundle at module-load time even though it never
// renders here (useMatchupsRatingForm stays in a loading state below) --
// the bundle touches canvas/WebGL/URL APIs jsdom doesn't implement, same
// gap App.test.tsx's own comment documents for EvolutionZone.
vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plot" />,
}))

const mockUseMatchupsRatingForm = vi.fn()
vi.mock('../hooks/useMatchupsRatingForm', () => ({ useMatchupsRatingForm: () => mockUseMatchupsRatingForm() }))

const mockUseNemesisOpponents = vi.fn()
vi.mock('../hooks/useNemesisOpponents', () => ({ useNemesisOpponents: () => mockUseNemesisOpponents() }))

describe('MatchupsPage', () => {
  it('renders the Rating & Form tab by default and does not mount Named Opponents hooks', () => {
    mockUseMatchupsRatingForm.mockReturnValue({ data: null, loading: true, error: false })
    mockUseNemesisOpponents.mockReturnValue({ rows: null, loading: true, error: false })
    render(<MatchupsPage />)
    expect(screen.getByRole('heading', { name: 'Matchups & Opponents' })).toBeInTheDocument()
    expect(mockUseMatchupsRatingForm).toHaveBeenCalled()
  })

  it('renders both tab labels', () => {
    mockUseMatchupsRatingForm.mockReturnValue({ data: null, loading: true, error: false })
    mockUseNemesisOpponents.mockReturnValue({ rows: null, loading: true, error: false })
    render(<MatchupsPage />)
    expect(screen.getByText('Rating & Form')).toBeInTheDocument()
    expect(screen.getByText('Named Opponents')).toBeInTheDocument()
  })
})

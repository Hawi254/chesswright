import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PatternsPage from './PatternsPage'
import { usePatternsSummary } from '../hooks/usePatternsSummary'
import { usePatternsClockTime } from '../hooks/usePatternsClockTime'
import { usePatternsTurningPoints } from '../hooks/usePatternsTurningPoints'
import { usePatternsPieces } from '../hooks/usePatternsPieces'
import { usePatternsPositions } from '../hooks/usePatternsPositions'
import { usePatternsGameContext } from '../hooks/usePatternsGameContext'
import { usePatternsComparisons } from '../hooks/usePatternsComparisons'
import { usePatternsSessions } from '../hooks/usePatternsSessions'

vi.mock('react-plotly.js', () => ({ default: () => <div data-testid="plot" /> }))
vi.mock('../hooks/usePatternsSummary')
vi.mock('../hooks/usePatternsClockTime')
vi.mock('../hooks/usePatternsTurningPoints')
vi.mock('../hooks/usePatternsPieces')
vi.mock('../hooks/usePatternsPositions')
vi.mock('../hooks/usePatternsGameContext')
vi.mock('../hooks/usePatternsComparisons')
vi.mock('../hooks/usePatternsSessions')

const mockUsePatternsSummary = vi.mocked(usePatternsSummary)
const mockUsePatternsClockTime = vi.mocked(usePatternsClockTime)
const mockUsePatternsTurningPoints = vi.mocked(usePatternsTurningPoints)
const mockUsePatternsPieces = vi.mocked(usePatternsPieces)
const mockUsePatternsPositions = vi.mocked(usePatternsPositions)
const mockUsePatternsGameContext = vi.mocked(usePatternsGameContext)
const mockUsePatternsComparisons = vi.mocked(usePatternsComparisons)
const mockUsePatternsSessions = vi.mocked(usePatternsSessions)

const CARDS = [
  { tab_id: 'clock-time', label: 'Clock & Time', headline: 'h1', detail: 'd1' },
  { tab_id: 'turning-points', label: 'Turning Points', headline: 'h2', detail: 'd2' },
  { tab_id: 'piece-handling', label: 'Piece Handling', headline: 'h3', detail: 'd3' },
  { tab_id: 'positions', label: 'Positions', headline: 'h4', detail: 'd4' },
  { tab_id: 'game-context', label: 'Game Context', headline: 'h5', detail: 'd5' },
  { tab_id: 'comparisons', label: 'Comparisons', headline: 'h6', detail: 'd6' },
  { tab_id: 'sessions', label: 'Playing Sessions', headline: 'h7', detail: 'd7' },
]

function mockAllLoading() {
  mockUsePatternsSummary.mockReturnValue({ cards: null, loading: true, error: false })
  mockUsePatternsClockTime.mockReturnValue({ data: null, loading: true, error: false })
  mockUsePatternsTurningPoints.mockReturnValue({ data: null, loading: true, error: false })
  mockUsePatternsPieces.mockReturnValue({ data: null, loading: true, error: false })
  mockUsePatternsPositions.mockReturnValue({ data: null, loading: true, error: false })
  mockUsePatternsGameContext.mockReturnValue({ data: null, loading: true, error: false })
  mockUsePatternsComparisons.mockReturnValue({ data: null, loading: true, error: false })
  mockUsePatternsSessions.mockReturnValue({ data: null, loading: true, error: false })
}

describe('PatternsPage', () => {
  it('renders the heading and all seven tabs', () => {
    mockAllLoading()
    render(<PatternsPage />)
    expect(screen.getByRole('heading', { name: 'Patterns & Tendencies' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Clock & Time' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Turning Points' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Piece Handling' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Positions' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Game Context' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Comparisons' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Playing Sessions' })).toBeInTheDocument()
  })

  it('clicking the Comparisons scorecard card activates the Comparisons tab', () => {
    mockAllLoading()
    mockUsePatternsSummary.mockReturnValue({ cards: CARDS, loading: false, error: false })
    render(<PatternsPage />)
    fireEvent.click(screen.getByRole('button', { name: /Comparisons/ }))
    expect(screen.getByRole('tab', { name: 'Comparisons' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Clock & Time' })).toHaveAttribute('aria-selected', 'false')
  })

  it('clicking the Playing Sessions scorecard card activates the Playing Sessions tab', () => {
    mockAllLoading()
    mockUsePatternsSummary.mockReturnValue({ cards: CARDS, loading: false, error: false })
    render(<PatternsPage />)
    fireEvent.click(screen.getByRole('button', { name: /Playing Sessions/ }))
    expect(screen.getByRole('tab', { name: 'Playing Sessions' })).toHaveAttribute('aria-selected', 'true')
  })
})

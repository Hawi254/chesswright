import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PointsHeadline from './PointsHeadline'

describe('PointsHeadline', () => {
  it('renders nothing when headline is null', () => {
    const { container } = render(<PointsHeadline headline={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the failed-conversion sentence with its detail', () => {
    render(<PointsHeadline headline={{
      bucket: 'failed_conversion', nGames: 3, leaked: 10, totalLeaked: 12,
      detail: 'The costliest slice: positions that first became winning in the middlegame (7 pts).',
    }} />)
    expect(screen.getByText(/failed conversions/i)).toBeInTheDocument()
    expect(screen.getByText(/3 games/i)).toBeInTheDocument()
    expect(screen.getByText(/costliest slice/i)).toBeInTheDocument()
  })

  it('renders the missed-swindle sentence with no detail', () => {
    render(<PointsHeadline headline={{ bucket: 'missed_swindle', nGames: 1, leaked: 4, totalLeaked: 4, detail: null }} />)
    expect(screen.getByText(/missed swindles/i)).toBeInTheDocument()
    expect(screen.getByText(/1 game\b/i)).toBeInTheDocument()
    expect(screen.queryByText(/costliest slice/i)).not.toBeInTheDocument()
  })

  it('renders the failed-hold sentence', () => {
    render(<PointsHeadline headline={{ bucket: 'failed_hold', nGames: 2, leaked: 1, totalLeaked: 1, detail: null }} />)
    expect(screen.getByText(/failed holds/i)).toBeInTheDocument()
  })
})

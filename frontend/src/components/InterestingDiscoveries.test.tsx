import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InterestingDiscoveries from './InterestingDiscoveries'
import type { Finding } from '../hooks/useOverviewData'

describe('InterestingDiscoveries', () => {
  it('includes neutral-polarity findings', () => {
    const findings: Finding[] = [
      { title: 'Tactical highlights so far', headline: 'h', detail: 'd', polarity: 'neutral', severity: 'low', category: 'tactical' },
    ]
    render(<InterestingDiscoveries findings={findings} />)
    expect(screen.getByText('Tactical highlights so far')).toBeInTheDocument()
  })

  it('includes a high-severity matchup finding (surprise-gap proxy) even though its polarity is not neutral', () => {
    const findings: Finding[] = [
      { title: 'Toughest opponent', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'matchup' },
    ]
    render(<InterestingDiscoveries findings={findings} />)
    expect(screen.getByText('Toughest opponent')).toBeInTheDocument()
  })

  it('excludes a low/medium-severity matchup finding', () => {
    const findings: Finding[] = [
      { title: 'Toughest opponent', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'medium', category: 'matchup' },
    ]
    render(<InterestingDiscoveries findings={findings} />)
    expect(screen.queryByText('Toughest opponent')).not.toBeInTheDocument()
  })

  it('excludes an ordinary weakness/strength finding outside matchup/neutral', () => {
    const findings: Finding[] = [
      { title: 'Piece blunder hot-spot', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'tactical' },
    ]
    render(<InterestingDiscoveries findings={findings} />)
    expect(screen.queryByText('Piece blunder hot-spot')).not.toBeInTheDocument()
  })

  it('renders nothing when no finding qualifies', () => {
    const { container } = render(<InterestingDiscoveries findings={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

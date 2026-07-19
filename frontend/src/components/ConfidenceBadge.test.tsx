import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ConfidenceBadge from './ConfidenceBadge'

describe('ConfidenceBadge', () => {
  it('renders the Low label and a 33% width bar', () => {
    render(<ConfidenceBadge tier="low" />)
    expect(screen.getByText(/Low confidence/)).toBeInTheDocument()
  })

  it('renders the Medium label', () => {
    render(<ConfidenceBadge tier="medium" />)
    expect(screen.getByText(/Medium confidence/)).toBeInTheDocument()
  })

  it('renders the High label', () => {
    render(<ConfidenceBadge tier="high" />)
    expect(screen.getByText(/High confidence/)).toBeInTheDocument()
  })

  it('appends the sample size when given', () => {
    render(<ConfidenceBadge tier="low" sampleSize={7} />)
    expect(screen.getByText(/Low confidence — 7 games/)).toBeInTheDocument()
  })

  it('omits the sample-size suffix when not given', () => {
    render(<ConfidenceBadge tier="low" />)
    expect(screen.queryByText(/games/)).not.toBeInTheDocument()
  })
})

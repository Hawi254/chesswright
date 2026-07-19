import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InsightCard from './InsightCard'
import type { Finding } from '../hooks/useOverviewData'
import type { RelatedFindingPair } from '../lib/relatedFindings'

const BASE_FINDING: Finding = {
  title: 'Piece blunder hot-spot',
  headline: 'Knight moves blunder at 12.0%',
  detail: '2.0x your overall blunder rate, over 200 analyzed Knight moves.',
  polarity: 'weakness',
  severity: 'high',
  category: 'tactical',
  confidence: 'high',
  sample_size: 200,
}

describe('InsightCard', () => {
  it('renders title, headline, and detail', () => {
    render(<InsightCard finding={BASE_FINDING} />)
    expect(screen.getByText('Piece blunder hot-spot')).toBeInTheDocument()
    expect(screen.getByText('Knight moves blunder at 12.0%')).toBeInTheDocument()
    expect(screen.getByText(/2.0x your overall blunder rate/)).toBeInTheDocument()
  })

  it('maps severity to the Critical/Moderate/Minor label', () => {
    render(<InsightCard finding={{ ...BASE_FINDING, severity: 'high' }} />)
    expect(screen.getByText('Critical')).toBeInTheDocument()
  })

  it('maps category to its display label per decision 1', () => {
    render(<InsightCard finding={{ ...BASE_FINDING, category: 'matchup' }} />)
    expect(screen.getByText('Matchups & Opponents')).toBeInTheDocument()
  })

  it('renders a confidence bar with tier and sample size when both are present', () => {
    render(<InsightCard finding={BASE_FINDING} />)
    expect(screen.getByText(/High confidence — 200 games/)).toBeInTheDocument()
  })

  it('omits the confidence bar when confidence/sample_size are absent', () => {
    const { confidence, sample_size, ...rest } = BASE_FINDING
    render(<InsightCard finding={rest as Finding} />)
    expect(screen.queryByText(/confidence —/)).not.toBeInTheDocument()
  })

  it('renders no action button', () => {
    render(<InsightCard finding={BASE_FINDING} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders the related-finding footer when relatedTo is provided', () => {
    const pair: RelatedFindingPair = {
      titles: ['Piece blunder hot-spot', 'Clock pressure and blunder rate'],
      rationale: 'Clock pressure may be part of what drives the piece hot-spot too.',
      source: 'Chabris & Hearst (2006)',
    }
    render(<InsightCard finding={BASE_FINDING} relatedTo={pair} />)
    expect(screen.getByText(/Related: Clock pressure and blunder rate/)).toBeInTheDocument()
    expect(screen.getByText(/Chabris & Hearst \(2006\)/)).toBeInTheDocument()
  })

  it('renders nothing extra when relatedTo is null (default, unchanged behavior)', () => {
    render(<InsightCard finding={BASE_FINDING} />)
    expect(screen.queryByText(/Related:/)).not.toBeInTheDocument()
  })
})

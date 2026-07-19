import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RangeHeadline from './RangeHeadline'
import type { BatchImpactHeadline } from '../hooks/useBatchImpact'

const HEADLINE: BatchImpactHeadline = {
  gamesInRange: 5, acplBefore: 40, acplAfter: 30,
  blunderRateBefore: 10, blunderRateAfter: 6,
  newBlunders: 2, newBrilliant: 1, topMotif: 'fork', topMotifCount: 2,
}

describe('RangeHeadline', () => {
  it('renders the range label', () => {
    render(<RangeHeadline headline={HEADLINE} pendingAnnotation={false} runALabel="Run #1" runBLabel="Run #2" />)
    expect(screen.getByText('Between Run #1 and Run #2')).toBeInTheDocument()
  })

  it('renders the four headline figures when not pending', () => {
    render(<RangeHeadline headline={HEADLINE} pendingAnnotation={false} runALabel="Run #1" runBLabel="Run #2" />)
    expect(screen.getByText('40.0 → 30.0')).toBeInTheDocument()
    expect(screen.getByText('10.0% → 6.0%')).toBeInTheDocument()
    expect(screen.getByText('2 / 1')).toBeInTheDocument()
    expect(screen.getByText('fork (2)')).toBeInTheDocument()
  })

  it('renders the pendingAnnotation banner instead of figures when pending', () => {
    render(<RangeHeadline headline={null} pendingAnnotation runALabel="Run #1" runBLabel="Run #2" />)
    expect(screen.getByText(/hasn't been through the annotation pass yet/)).toBeInTheDocument()
    expect(screen.queryByText(/→/)).not.toBeInTheDocument()
  })

  it('renders an em-dash for a first-batch (no before) headline', () => {
    const firstBatch = { ...HEADLINE, acplBefore: null, blunderRateBefore: null }
    render(<RangeHeadline headline={firstBatch} pendingAnnotation={false} runALabel="Start" runBLabel="Run #1" />)
    expect(screen.getByText('— → 30.0')).toBeInTheDocument()
  })
})

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StrengthsWeaknesses from './StrengthsWeaknesses'
import type { Finding } from '../hooks/useOverviewData'

const FINDINGS: Finding[] = [
  { title: 'Strong tactics', headline: 'h', detail: 'd', polarity: 'strength', severity: 'medium', category: 'tactical' },
  { title: 'Weak endgame', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'defense' },
  { title: 'Mixed timing', headline: 'h', detail: 'd', polarity: 'mixed', severity: 'low', category: 'time' },
  { title: 'Neutral fact', headline: 'h', detail: 'd', polarity: 'neutral', severity: 'low', category: 'general' },
]

describe('StrengthsWeaknesses', () => {
  it('renders only strength findings in the strengths column', () => {
    render(<StrengthsWeaknesses findings={FINDINGS} />)
    const strengths = screen.getByTestId('strengths-column')
    expect(within(strengths).getByText('Strong tactics')).toBeInTheDocument()
    expect(within(strengths).queryByText('Weak endgame')).not.toBeInTheDocument()
    expect(within(strengths).queryByText('Mixed timing')).not.toBeInTheDocument()
  })

  it('renders only weakness findings in the weaknesses column, excluding mixed/neutral', () => {
    render(<StrengthsWeaknesses findings={FINDINGS} />)
    const weaknesses = screen.getByTestId('weaknesses-column')
    expect(within(weaknesses).getByText('Weak endgame')).toBeInTheDocument()
    expect(within(weaknesses).queryByText('Mixed timing')).not.toBeInTheDocument()
    expect(within(weaknesses).queryByText('Neutral fact')).not.toBeInTheDocument()
  })

  it('shows the empty-state caption when a column has nothing', () => {
    render(<StrengthsWeaknesses findings={[FINDINGS[1]]} />)
    expect(screen.getByText('Nothing tagged as a clear strength yet with the data analyzed so far.')).toBeInTheDocument()
  })
})

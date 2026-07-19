import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import HeroInsight from './HeroInsight'
import type { Finding } from '../hooks/useOverviewData'

const FINDING: Finding = {
  title: 'Piece blunder hot-spot',
  headline: 'Knight moves blunder at 12.0%',
  detail: '2.0x your overall blunder rate.',
  polarity: 'weakness',
  severity: 'high',
  category: 'tactical',
}

describe('HeroInsight', () => {
  it('renders the finding as a hero-variant InsightCard', () => {
    render(<HeroInsight finding={FINDING} />)
    expect(screen.getByText('Piece blunder hot-spot')).toBeInTheDocument()
    expect(screen.getByText('Knight moves blunder at 12.0%')).toBeInTheDocument()
    expect(screen.getByTestId('insight-card')).toBeInTheDocument()
  })
})

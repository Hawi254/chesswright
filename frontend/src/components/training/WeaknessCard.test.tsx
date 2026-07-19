import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import WeaknessCard from './WeaknessCard'
import type { Finding } from '../../hooks/useOverviewData'

const PRESET_FINDING: Finding = {
  title: 'Piece blunder hot-spot', headline: 'h', detail: 'd',
  polarity: 'weakness', severity: 'high', category: 'tactical',
}
const NO_PRESET_FINDING: Finding = {
  title: 'Toughest opponent', headline: 'h', detail: 'd',
  polarity: 'weakness', severity: 'medium', category: 'matchup',
}

describe('WeaknessCard', () => {
  it('shows a build-practice-set button when the finding has a drill preset', () => {
    render(<MemoryRouter><WeaknessCard finding={PRESET_FINDING} /></MemoryRouter>)
    expect(screen.getByRole('button', { name: /Build practice set/i })).toBeInTheDocument()
  })

  it('omits the action button when the finding has no drill preset', () => {
    render(<MemoryRouter><WeaknessCard finding={NO_PRESET_FINDING} /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: /Build practice set/i })).not.toBeInTheDocument()
  })
})

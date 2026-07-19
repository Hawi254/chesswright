import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import CoachingZone from './CoachingZone'
import type { Finding } from '../hooks/useOverviewData'

function renderZone(findings: Finding[], cached: boolean | null) {
  return render(
    <MemoryRouter>
      <CoachingZone findings={findings} cached={cached} />
    </MemoryRouter>,
  )
}

describe('CoachingZone', () => {
  it('renders the zone head, CTA, and quick links but no preview/ranked sections when findings is empty', () => {
    renderZone([], null)

    expect(screen.getByText('What to work on')).toBeInTheDocument()
    expect(screen.getByText('Your coaching plan')).toBeInTheDocument()
    expect(screen.getByText('Get your coaching plan →')).toBeInTheDocument()
    expect(screen.getByText('Insights')).toBeInTheDocument()
    expect(screen.getByText('Patterns & Tendencies')).toBeInTheDocument()
    expect(screen.getByText('Openings & Repertoire')).toBeInTheDocument()
    expect(screen.queryByTestId('coaching-preview-grid')).not.toBeInTheDocument()
    expect(screen.queryByTestId('coaching-ranked-list')).not.toBeInTheDocument()
  })

  it('shows "Get your coaching plan" when cached is false', () => {
    renderZone([], false)
    expect(screen.getByText('Get your coaching plan →')).toBeInTheDocument()
  })

  it('shows "View your coaching plan" when cached is true', () => {
    renderZone([], true)
    expect(screen.getByText('View your coaching plan →')).toBeInTheDocument()
  })

  it('splits findings into Strengths/Mixed/Focus-areas preview columns, keeps the ranked list\'s weakness-or-mixed eligibility unchanged, and links mapped findings to their origin page', () => {
    const findings: Finding[] = [
      { title: 'Sharp attacker', headline: 'h', detail: 'Finds tactics often',
        polarity: 'strength', severity: 'medium', category: 'tactical' },
      { title: 'Solid defense', headline: 'h', detail: 'Rarely blunders material',
        polarity: 'strength', severity: 'low', category: 'defense' },
      { title: 'Piece blunder hot-spot', headline: 'h', detail: 'Loses pieces under pressure',
        polarity: 'weakness', severity: 'high', category: 'tactical' },
      { title: 'Unmapped finding', headline: 'h', detail: 'No destination page for this one',
        polarity: 'weakness', severity: 'medium', category: 'general' },
      { title: 'Toughest opponent', headline: 'h', detail: 'Struggles against this player',
        polarity: 'mixed', severity: 'low', category: 'matchup' },
    ]
    renderZone(findings, null)

    const preview = screen.getByTestId('coaching-preview-grid')
    expect(within(preview).getByText('Sharp attacker')).toBeInTheDocument()
    expect(within(preview).getByText('Solid defense')).toBeInTheDocument()
    expect(within(preview).getByText('Piece blunder hot-spot')).toBeInTheDocument()
    expect(within(preview).getByText('Unmapped finding')).toBeInTheDocument()
    // 'Toughest opponent' is the sole 'mixed' finding -- it gets its own
    // preview column now, independent of the ranked list's cap below.
    expect(within(preview).getByText('Toughest opponent')).toBeInTheDocument()

    // Ranked-list eligibility is UNCHANGED from before this task: the old
    // splitByPolarity's weakness-or-mixed bucket, capped at 2 in list
    // order, before severity sort/slice(3) ever applies -- 'Toughest
    // opponent' is 3rd in that combined pool and stays excluded here even
    // though it now appears in the preview grid above.
    const ranked = screen.getByTestId('coaching-ranked-list')
    expect(within(ranked).queryByText('Toughest opponent')).not.toBeInTheDocument()
    expect(within(ranked).getByText('Piece blunder hot-spot')).toBeInTheDocument()
    expect(within(ranked).getByText('Unmapped finding')).toBeInTheDocument()

    expect(screen.getByText('Piece blunder hot-spot', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/is your top focus area/)).toBeInTheDocument()

    const patternsLinks = screen.getAllByRole('link', { name: 'Patterns & Tendencies' })
    expect(patternsLinks.length).toBeGreaterThan(0)
    patternsLinks.forEach((link) => expect(link).toHaveAttribute('href', '/patterns'))

    expect(screen.queryByRole('link', { name: /Unmapped/ })).not.toBeInTheDocument()
  })

  it('renders no ranked focus-area link for findings with no _FINDING_DEST mapping', () => {
    const findings: Finding[] = [
      { title: 'Some novel finding', headline: 'h', detail: 'd',
        polarity: 'weakness', severity: 'high', category: 'general' },
    ]
    renderZone(findings, null)

    const ranked = screen.getByTestId('coaching-ranked-list')
    expect(within(ranked).getByText('Some novel finding')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Some novel finding' })).not.toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CategorizedInsights from './CategorizedInsights'
import * as relatedFindingsModule from '../lib/relatedFindings'
import type { Finding } from '../hooks/useOverviewData'

const FINDINGS: Finding[] = [
  { title: 'Tactic A', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'tactical' },
  { title: 'Tactic B', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'tactical' },
  { title: 'Matchup A', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'medium', category: 'matchup' },
]

const PAIRED_FINDINGS: Finding[] = [
  { title: 'Clock pressure and blunder rate', headline: 'h', detail: 'd',
    polarity: 'weakness', severity: 'medium', category: 'time' },
  { title: 'Piece blunder hot-spot', headline: 'h', detail: 'd',
    polarity: 'weakness', severity: 'high', category: 'tactical' },
]

describe('CategorizedInsights', () => {
  it('groups findings by category using decision-1 display labels', () => {
    render(<CategorizedInsights findings={FINDINGS} />)
    // "Tactical"/"Matchups & Opponents" each render twice -- once as the
    // group heading, once per InsightCard's own category chip -- so this
    // asserts presence via getAllByText, not getByText (which throws on
    // more than one match).
    expect(screen.getAllByText('Tactical').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Matchups & Opponents').length).toBeGreaterThan(0)
    expect(screen.getByText('Tactic A')).toBeInTheDocument()
    expect(screen.getByText('Tactic B')).toBeInTheDocument()
    expect(screen.getByText('Matchup A')).toBeInTheDocument()
  })

  it('omits categories with zero findings entirely', () => {
    render(<CategorizedInsights findings={FINDINGS} />)
    expect(screen.queryByText('Time Management')).not.toBeInTheDocument()
    expect(screen.queryByText('King Safety')).not.toBeInTheDocument()
    expect(screen.queryByText('Giant-Killing & Collapses')).not.toBeInTheDocument()
    expect(screen.queryByText('General')).not.toBeInTheDocument()
  })

  it('shows an empty-state message when findings is empty', () => {
    render(<CategorizedInsights findings={[]} />)
    expect(screen.getByText(/Nothing categorized yet/)).toBeInTheDocument()
  })

  it('renders the related-finding footer on both cards when both paired titles are present', () => {
    render(<CategorizedInsights findings={PAIRED_FINDINGS} />)
    expect(screen.getByText(/Related: Piece blunder hot-spot/)).toBeInTheDocument()
    expect(screen.getByText(/Related: Clock pressure and blunder rate/)).toBeInTheDocument()
  })

  it('omits the footer when only one paired title is present', () => {
    render(<CategorizedInsights findings={[PAIRED_FINDINGS[0]]} />)
    expect(screen.queryByText(/Related:/)).not.toBeInTheDocument()
  })

  it('calls relatedFindingFor exactly once per rendered card, not recomputed pathologically', () => {
    const spy = vi.spyOn(relatedFindingsModule, 'relatedFindingFor')
    render(<CategorizedInsights findings={FINDINGS} />)
    expect(spy).toHaveBeenCalledTimes(FINDINGS.length)
    spy.mockRestore()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NemesisTable from './NemesisTable'
import type { NemesisRow } from '../hooks/useNemesisOpponents'

function row(overrides: Partial<NemesisRow> = {}): NemesisRow {
  return {
    opponent_name: 'Rival', n: 10, wins: 3, draws: 2, losses: 5, all_lichess: true, n_rated: 10,
    score_pct: 40.0, expected_score_pct: 50.0, surprise_pct: -10.0, confidence_tier: 'medium',
    ...overrides,
  }
}

describe('NemesisTable', () => {
  it('renders nothing for an empty list', () => {
    const { container } = render(<NemesisTable rows={[]} title="Toughest" onSelect={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the record and score for each row, plus a confidence badge', () => {
    render(<NemesisTable rows={[row()]} title="Toughest" onSelect={vi.fn()} />)
    expect(screen.getByText('Rival')).toBeInTheDocument()
    expect(screen.getByText('3-2-5')).toBeInTheDocument()
    expect(screen.getByText(/40\.0/)).toBeInTheDocument()
    expect(screen.getByText(/Medium confidence/)).toBeInTheDocument()
  })

  it('omits Expected %/Surprise columns by default', () => {
    render(<NemesisTable rows={[row()]} title="Toughest" onSelect={vi.fn()} />)
    expect(screen.queryByText('Expected %')).not.toBeInTheDocument()
    expect(screen.queryByText('Surprise')).not.toBeInTheDocument()
  })

  it('shows Expected %/Surprise columns when showExpectedSurprise is true', () => {
    render(<NemesisTable rows={[row()]} title="Surprises" showExpectedSurprise onSelect={vi.fn()} />)
    expect(screen.getByText('Expected %')).toBeInTheDocument()
    expect(screen.getByText('Surprise')).toBeInTheDocument()
    expect(screen.getByText(/-10\.0/)).toBeInTheDocument()
  })

  it('calls onSelect with the opponent name when a row is clicked', () => {
    const onSelect = vi.fn()
    render(<NemesisTable rows={[row()]} title="Toughest" onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Rival'))
    expect(onSelect).toHaveBeenCalledWith('Rival')
  })
})

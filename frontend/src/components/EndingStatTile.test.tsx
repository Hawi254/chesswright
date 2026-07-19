import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EndingStatTile from './EndingStatTile'

describe('EndingStatTile', () => {
  it('renders label, value, and detail', () => {
    render(<EndingStatTile label="Total games" value="2,847 games" detail="71% decisive, 29% draws" />)
    expect(screen.getByText('Total games')).toBeInTheDocument()
    expect(screen.getByText('2,847 games')).toBeInTheDocument()
    expect(screen.getByText('71% decisive, 29% draws')).toBeInTheDocument()
  })

  it('renders a muted empty state instead of a stat when value is null', () => {
    render(<EndingStatTile label="Total games" value={null} />)
    expect(screen.getByText('Not enough games yet.')).toBeInTheDocument()
    expect(screen.queryByText('Total games')).toBeInTheDocument() // label still shows
  })

  it('applies negative tone to the value text', () => {
    render(<EndingStatTile label="Flagged while ahead" value="18%" tone="negative" />)
    expect(screen.getByText('18%')).toHaveClass('text-negative')
  })

  it('renders children below the stat', () => {
    render(
      <EndingStatTile label="Explained" value="62% explained">
        <div data-testid="waffle-slot" />
      </EndingStatTile>,
    )
    expect(screen.getByTestId('waffle-slot')).toBeInTheDocument()
  })
})

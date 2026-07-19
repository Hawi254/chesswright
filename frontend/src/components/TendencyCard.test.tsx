import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TendencyCard from './TendencyCard'

describe('TendencyCard', () => {
  it('renders label, headline, and detail, and calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(
      <TendencyCard
        label="Clock & Time"
        headline='Blunder rate peaks at 12.0% with "critical (<5%)" clock left'
        detail='vs. 3.0% with "plenty (60-100%)" clock left'
        onClick={onClick}
      />,
    )
    expect(screen.getByText('Clock & Time')).toBeInTheDocument()
    expect(screen.getByText(/Blunder rate peaks at 12.0%/)).toBeInTheDocument()
    expect(screen.getByText(/vs\. 3\.0%/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

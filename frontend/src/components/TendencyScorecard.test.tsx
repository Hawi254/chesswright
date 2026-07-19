import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TendencyScorecard from './TendencyScorecard'
import { usePatternsSummary } from '../hooks/usePatternsSummary'

vi.mock('../hooks/usePatternsSummary')
const mockUsePatternsSummary = vi.mocked(usePatternsSummary)

describe('TendencyScorecard', () => {
  it('renders nothing while loading', () => {
    mockUsePatternsSummary.mockReturnValue({ cards: null, loading: true, error: false })
    const { container } = render(<TendencyScorecard onSelectTab={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    mockUsePatternsSummary.mockReturnValue({ cards: null, loading: false, error: true })
    const { container } = render(<TendencyScorecard onSelectTab={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when there are no cards yet', () => {
    mockUsePatternsSummary.mockReturnValue({ cards: [], loading: false, error: false })
    const { container } = render(<TendencyScorecard onSelectTab={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a card per entry and activates its tab on click', () => {
    mockUsePatternsSummary.mockReturnValue({
      cards: [
        {
          tab_id: 'clock-time',
          label: 'Clock & Time',
          headline: 'Blunder rate peaks at 12.0% with "critical (<5%)" clock left',
          detail: 'vs. 3.0% with "plenty (60-100%)" clock left',
        },
      ],
      loading: false,
      error: false,
    })
    const onSelectTab = vi.fn()
    render(<TendencyScorecard onSelectTab={onSelectTab} />)
    fireEvent.click(screen.getByRole('button', { name: /Clock & Time/ }))
    expect(onSelectTab).toHaveBeenCalledWith('clock-time')
  })
})

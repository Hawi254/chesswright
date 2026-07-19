import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PointsConversionBreakdown from './PointsConversionBreakdown'

vi.mock('react-plotly.js', () => ({ default: () => <div data-testid="plot" /> }))

describe('PointsConversionBreakdown', () => {
  it('renders nothing when there is no failed-conversion detail', () => {
    const { container } = render(<PointsConversionBreakdown advBand={[]} convPhase={[]} convClock={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders three charts when there is failed-conversion detail', () => {
    render(
      <PointsConversionBreakdown
        advBand={[{ adv_band: 'winning (80-90%)', n_games: 2, leaked: 3 }]}
        convPhase={[{ conv_phase: 'middlegame', n_games: 2, leaked: 3 }]}
        convClock={[{ conv_clock: 'no clock data', n_games: 2, leaked: 3 }]}
      />,
    )
    expect(screen.getAllByTestId('plot')).toHaveLength(3)
  })
})

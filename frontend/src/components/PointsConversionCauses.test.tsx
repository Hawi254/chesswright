import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PointsConversionCauses from './PointsConversionCauses'

vi.mock('react-plotly.js', () => ({ default: () => <div data-testid="plot" /> }))

describe('PointsConversionCauses', () => {
  it('renders nothing when there is no failed-conversion detail', () => {
    const { container } = render(<PointsConversionCauses reason={[]} piece={[]} mate={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the reason chart with mapped display labels via title, plus piece/mate charts when present', () => {
    render(
      <PointsConversionCauses
        reason={[{ reason: 'hung_piece', n: 2, pct: 50 }, { reason: 'other', n: 2, pct: 50 }]}
        piece={[{ label: 'Queen', n: 1, pct: 100 }]}
        mate={[]}
      />,
    )
    expect(screen.getAllByTestId('plot')).toHaveLength(2)
    expect(screen.getByText('Which piece hung')).toBeInTheDocument()
  })

  it('shows an empty-data note for piece/mate when both are empty', () => {
    render(<PointsConversionCauses reason={[{ reason: 'other', n: 1, pct: 100 }]} piece={[]} mate={[]} />)
    expect(screen.getAllByText(/not enough data/i)).toHaveLength(2)
  })
})

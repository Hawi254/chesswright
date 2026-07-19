import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TrendArrow from './TrendArrow'

describe('TrendArrow', () => {
  it('renders nothing when delta is null', () => {
    const { container } = render(<TrendArrow delta={null} goodDirection="down" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a down arrow in the positive color when delta is negative and goodDirection is down', () => {
    render(<TrendArrow delta={-3.2} goodDirection="down" />)
    const el = screen.getByTestId('trend-arrow')
    expect(el).toHaveTextContent('▼3.2')
    expect(el.className).toContain('text-positive')
  })

  it('renders a down arrow in the negative color when delta is negative and goodDirection is up', () => {
    render(<TrendArrow delta={-3.2} goodDirection="up" />)
    const el = screen.getByTestId('trend-arrow')
    expect(el).toHaveTextContent('▼3.2')
    expect(el.className).toContain('text-negative')
  })

  it('renders an up arrow in the positive color when delta is positive and goodDirection is up', () => {
    render(<TrendArrow delta={2.1} goodDirection="up" />)
    const el = screen.getByTestId('trend-arrow')
    expect(el).toHaveTextContent('▲2.1')
    expect(el.className).toContain('text-positive')
  })

  it('appends the unit suffix when provided', () => {
    render(<TrendArrow delta={-0.8} goodDirection="down" unit="pp" />)
    expect(screen.getByTestId('trend-arrow')).toHaveTextContent('▼0.8pp')
  })

  it('renders a neutral "flat" label when delta is exactly 0', () => {
    render(<TrendArrow delta={0} goodDirection="up" />)
    expect(screen.getByTestId('trend-arrow')).toHaveTextContent('flat')
  })
})

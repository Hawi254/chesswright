import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DumbbellSection from './DumbbellSection'
import type { DumbbellRow } from '../lib/charts'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const ROWS: DumbbellRow[] = [
  { category: 'opening', before: 20, after: 18 },
  { category: 'middlegame', before: 30, after: 45 },
]

describe('DumbbellSection', () => {
  beforeEach(() => plotMock.mockClear())

  it('renders the title and a Plot built from dumbbellChart', () => {
    render(<DumbbellSection title="ACPL" rows={ROWS} xTitle="ACPL" />)
    expect(screen.getByText('ACPL')).toBeInTheDocument()
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(plotMock.mock.calls[0][0].data).toHaveLength(2)
  })

  it('renders an optional caption', () => {
    render(<DumbbellSection title="ACPL" caption="Sorted by biggest change" rows={ROWS} xTitle="ACPL" />)
    expect(screen.getByText('Sorted by biggest change')).toBeInTheDocument()
  })

  it('renders a "not enough data" message instead of a chart when rows is empty', () => {
    render(<DumbbellSection title="ACPL" rows={[]} xTitle="ACPL" />)
    expect(plotMock).not.toHaveBeenCalled()
    expect(screen.getByText('Not enough data yet in this range.')).toBeInTheDocument()
  })
})

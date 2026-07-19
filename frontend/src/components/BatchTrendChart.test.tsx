import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BatchTrendChart from './BatchTrendChart'
import type { BatchImpactTrendRow } from '../hooks/useBatchImpact'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const ROWS: BatchImpactTrendRow[] = [
  { runId: 1, endedAt: '2026-07-01', gamesAnalyzed: 5, cumulativeAcpl: 40, cumulativeBlunderRate: 10 },
  { runId: 2, endedAt: '2026-07-02', gamesAnalyzed: 5, cumulativeAcpl: 30, cumulativeBlunderRate: 8 },
  { runId: 3, endedAt: '2026-07-03', gamesAnalyzed: 5, cumulativeAcpl: 20, cumulativeBlunderRate: 5 },
]

describe('BatchTrendChart', () => {
  beforeEach(() => plotMock.mockClear())

  it('renders a Plot with one point per annotated run', () => {
    render(
      <BatchTrendChart rows={ROWS} yKey="cumulativeAcpl" yTitle="ACPL" color="#3987e5"
        range={{ runA: 1, runB: 2 }} onPointClick={vi.fn()} />,
    )
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(plotMock.mock.calls[0][0].data[0].x).toEqual([1, 2, 3])
  })

  it('shows a "not enough" message instead of a chart when fewer than 2 annotated runs exist', () => {
    render(
      <BatchTrendChart rows={[ROWS[0]]} yKey="cumulativeAcpl" yTitle="ACPL" color="#3987e5"
        range={{ runA: null, runB: 1 }} onPointClick={vi.fn()} />,
    )
    expect(plotMock).not.toHaveBeenCalled()
    expect(screen.getByText(/not enough annotated batches/i)).toBeInTheDocument()
  })

  it('calls onPointClick with the clicked run id', () => {
    const onPointClick = vi.fn()
    render(
      <BatchTrendChart rows={ROWS} yKey="cumulativeAcpl" yTitle="ACPL" color="#3987e5"
        range={{ runA: 1, runB: 2 }} onPointClick={onPointClick} />,
    )
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ customdata: 3 }] })
    expect(onPointClick).toHaveBeenCalledWith(3)
  })

  it('does nothing on a click event with no points', () => {
    const onPointClick = vi.fn()
    render(
      <BatchTrendChart rows={ROWS} yKey="cumulativeAcpl" yTitle="ACPL" color="#3987e5"
        range={{ runA: 1, runB: 2 }} onPointClick={onPointClick} />,
    )
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [] })
    expect(onPointClick).not.toHaveBeenCalled()
  })
})

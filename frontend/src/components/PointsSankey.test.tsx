import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PointsSankey from './PointsSankey'
import type { PointsBucketSummary } from '../hooks/usePointsLedger'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const BUCKETS: PointsBucketSummary[] = [
  { bucket: 'failed_conversion', n_games: 5, leaked: 12 },
  { bucket: 'failed_hold', n_games: 2, leaked: 1 },
]

describe('PointsSankey', () => {
  beforeEach(() => plotMock.mockClear())

  it('renders a Plot built from sankeyChart', () => {
    render(<PointsSankey buckets={BUCKETS} actualPoints={40} leakedPoints={13} onBucketClick={vi.fn()} />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(plotMock.mock.calls[0][0].data[0].type).toBe('sankey')
  })

  it('calls onBucketClick with the raw bucket key when a bucket node is clicked', () => {
    const onBucketClick = vi.fn()
    render(<PointsSankey buckets={BUCKETS} actualPoints={40} leakedPoints={13} onBucketClick={onBucketClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ customdata: 'failed_conversion' }] })
    expect(onBucketClick).toHaveBeenCalledWith('failed_conversion')
  })

  it('does nothing when the clicked point has no customdata (Root/Kept/Leaked)', () => {
    const onBucketClick = vi.fn()
    render(<PointsSankey buckets={BUCKETS} actualPoints={40} leakedPoints={13} onBucketClick={onBucketClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ customdata: null }] })
    expect(onBucketClick).not.toHaveBeenCalled()
  })

  it('does nothing on a click event with no points', () => {
    const onBucketClick = vi.fn()
    render(<PointsSankey buckets={BUCKETS} actualPoints={40} leakedPoints={13} onBucketClick={onBucketClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [] })
    expect(onBucketClick).not.toHaveBeenCalled()
  })
})

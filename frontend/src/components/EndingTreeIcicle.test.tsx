import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EndingTreeIcicle from './EndingTreeIcicle'
import type { EndingTree } from '../lib/endingTree'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const TREE: EndingTree = {
  ids: ['root', 'win', 'loss'],
  labels: ['All games', 'Win', 'Loss'],
  parents: ['', 'root', 'root'],
  values: [10, 4, 6],
}

describe('EndingTreeIcicle', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders a Plot with the tree data', () => {
    render(<EndingTreeIcicle tree={TREE} onNodeClick={vi.fn()} />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(plotMock.mock.calls[0][0].data[0].ids).toEqual(TREE.ids)
  })

  it('calls onNodeClick with the clicked node id', () => {
    const onNodeClick = vi.fn()
    render(<EndingTreeIcicle tree={TREE} onNodeClick={onNodeClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ id: 'loss' }] })
    expect(onNodeClick).toHaveBeenCalledWith('loss')
  })

  it('does nothing on a click event with no points', () => {
    const onNodeClick = vi.fn()
    render(<EndingTreeIcicle tree={TREE} onNodeClick={onNodeClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [] })
    expect(onNodeClick).not.toHaveBeenCalled()
  })
})

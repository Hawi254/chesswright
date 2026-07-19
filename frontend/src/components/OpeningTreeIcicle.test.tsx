import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OpeningTreeIcicle from './OpeningTreeIcicle'
import type { OpeningTreeMap } from '../lib/openingTreeMap'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const MAP: OpeningTreeMap = {
  ids: ['root', 'e4', 'e4/e5'],
  labels: ['Start', 'e4', 'e5'],
  parents: ['', 'root', 'e4'],
  values: [10, 8, 5],
  win_pct: [50, 62.5, 40],
  has_flip: [false, false, false],
}

describe('OpeningTreeIcicle', () => {
  beforeEach(() => plotMock.mockClear())

  it('renders a Plot with the map data', () => {
    render(<OpeningTreeIcicle map={MAP} onNodeClick={vi.fn()} />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    expect(plotMock.mock.calls[0][0].data[0].ids).toEqual(MAP.ids)
  })

  it('calls onNodeClick with the clicked node id split into a path', () => {
    const onNodeClick = vi.fn()
    render(<OpeningTreeIcicle map={MAP} onNodeClick={onNodeClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ id: 'e4/e5' }] })
    expect(onNodeClick).toHaveBeenCalledWith(['e4', 'e5'])
  })

  it('calls onNodeClick with an empty path for the root node', () => {
    const onNodeClick = vi.fn()
    render(<OpeningTreeIcicle map={MAP} onNodeClick={onNodeClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ id: 'root' }] })
    expect(onNodeClick).toHaveBeenCalledWith([])
  })

  it('does nothing on a click event with no points', () => {
    const onNodeClick = vi.fn()
    render(<OpeningTreeIcicle map={MAP} onNodeClick={onNodeClick} />)
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [] })
    expect(onNodeClick).not.toHaveBeenCalled()
  })
})

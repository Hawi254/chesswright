import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EvalGraph from './EvalGraph'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

describe('EvalGraph', () => {
  // plotMock is module-scope (hoisted) and shared across every it() in
  // this file -- without clearing, mock.calls[0][0] would read an
  // earlier test's render instead of this test's own (same bug found
  // live in Chessboard.test.tsx's identical pattern).
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('shows the not-enough-data message with fewer than 2 points', () => {
    render(<EvalGraph winProb={[]} currentPly={null} onSelectPly={vi.fn()} />)
    expect(screen.getByText(/Not enough annotated moves yet/)).toBeInTheDocument()
    expect(plotMock).not.toHaveBeenCalled()
  })

  it('renders a filled copper win-probability line', () => {
    render(
      <EvalGraph
        winProb={[{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }]}
        currentPly={1}
        onSelectPly={vi.fn()}
      />,
    )
    const props = plotMock.mock.calls[0][0]
    expect(props.data[0].y).toEqual([0.55, 0.4])
    expect(props.data[0].line.color).toBe('#E08A3C')
    expect(props.data[0].fill).toBe('tozeroy')
  })

  it('draws the 50% cyan reference line', () => {
    render(
      <EvalGraph
        winProb={[{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }]}
        currentPly={1}
        onSelectPly={vi.fn()}
      />,
    )
    const props = plotMock.mock.calls[0][0]
    expect(props.layout.shapes[0].y0).toBe(0.5)
    expect(props.layout.shapes[0].line.color).toBe('#4FB8C4')
  })

  it('adds a cyan marker trace at the current ply', () => {
    render(
      <EvalGraph
        winProb={[{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }]}
        currentPly={2}
        onSelectPly={vi.fn()}
      />,
    )
    const props = plotMock.mock.calls[0][0]
    const marker = props.data[1]
    expect(marker.x).toEqual([2])
    expect(marker.y).toEqual([0.4])
    expect(marker.marker.color).toBe('#4FB8C4')
  })

  it('omits the marker trace when currentPly has no matching point', () => {
    render(
      <EvalGraph
        winProb={[{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }]}
        currentPly={null}
        onSelectPly={vi.fn()}
      />,
    )
    const props = plotMock.mock.calls[0][0]
    expect(props.data).toHaveLength(1)
  })

  it('calls onSelectPly with the clicked point\'s ply on click', () => {
    const onSelectPly = vi.fn()
    render(
      <EvalGraph
        winProb={[{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }]}
        currentPly={1}
        onSelectPly={onSelectPly}
      />,
    )
    const props = plotMock.mock.calls[0][0]
    props.onClick({ points: [{ pointIndex: 1 }] })
    expect(onSelectPly).toHaveBeenCalledWith(2)
  })
})

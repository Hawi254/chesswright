import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Chessboard from './Chessboard'

const { boardMock } = vi.hoisted(() => ({ boardMock: vi.fn() }))

vi.mock('react-chessboard', () => ({
  Chessboard: (props: unknown) => {
    boardMock(props)
    return <div data-testid="board" />
  },
}))

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

describe('Chessboard', () => {
  // boardMock is module-scope (hoisted) and shared across every it() in
  // this file -- without clearing, mock.calls[0][0] silently reads an
  // earlier test's render instead of this test's own (found live: 3 of
  // 5 assertions still passed by coincidence since those props happened
  // to match across renders, but the last-move-highlight test read the
  // wrong render and failed).
  beforeEach(() => {
    boardMock.mockClear()
  })

  it('renders nothing when fen is undefined', () => {
    const { container } = render(
      <Chessboard fen={undefined} orientation="white" lastmoveFrom={null} lastmoveTo={null} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('passes the FEN and orientation through to react-chessboard', () => {
    render(<Chessboard fen={START_FEN} orientation="black" lastmoveFrom={null} lastmoveTo={null} />)
    const props = boardMock.mock.calls[0][0]
    expect(props.position).toBe(START_FEN)
    expect(props.boardOrientation).toBe('black')
  })

  it('is not interactive when the interactive prop is omitted', () => {
    render(<Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} />)
    const props = boardMock.mock.calls[0][0]
    expect(props.arePiecesDraggable).toBe(false)
  })

  it('highlights the last-move squares', () => {
    render(<Chessboard fen={START_FEN} orientation="white" lastmoveFrom="e2" lastmoveTo="e4" />)
    const props = boardMock.mock.calls[0][0]
    expect(props.customSquareStyles.e2).toEqual({ backgroundColor: 'rgba(255, 255, 102, 0.5)' })
    expect(props.customSquareStyles.e4).toEqual({ backgroundColor: 'rgba(255, 255, 102, 0.5)' })
  })

  it('recolors board squares away from react-chessboard defaults', () => {
    render(<Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} />)
    const props = boardMock.mock.calls[0][0]
    expect(props.customDarkSquareStyle).toEqual({ backgroundColor: '#8B5A2B' })
    expect(props.customLightSquareStyle).toEqual({ backgroundColor: '#ECDFC8' })
  })

  it('passes arrows through to react-chessboard as customArrows tuples', () => {
    render(
      <Chessboard
        fen={START_FEN}
        orientation="white"
        lastmoveFrom={null}
        lastmoveTo={null}
        arrows={[{ from: 'e2', to: 'e4', color: 'red' }, { from: 'g1', to: 'f3' }]}
      />,
    )
    const props = boardMock.mock.calls[0][0]
    expect(props.customArrows).toEqual([
      ['e2', 'e4', 'red'],
      ['g1', 'f3', undefined],
    ])
  })

  it('renders no customArrows when arrows is omitted', () => {
    render(<Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} />)
    const props = boardMock.mock.calls[0][0]
    expect(props.customArrows).toEqual([])
  })

  it('merges highlightedSquares into customSquareStyles alongside last-move highlighting', () => {
    render(
      <Chessboard
        fen={START_FEN}
        orientation="white"
        lastmoveFrom="e2"
        lastmoveTo="e4"
        highlightedSquares={{ f3: { backgroundColor: 'rgba(0, 200, 255, 0.4)' } }}
      />,
    )
    const props = boardMock.mock.calls[0][0]
    expect(props.customSquareStyles.e2).toEqual({ backgroundColor: 'rgba(255, 255, 102, 0.5)' })
    expect(props.customSquareStyles.e4).toEqual({ backgroundColor: 'rgba(255, 255, 102, 0.5)' })
    expect(props.customSquareStyles.f3).toEqual({ backgroundColor: 'rgba(0, 200, 255, 0.4)' })
  })

  it('is draggable when interactive', () => {
    render(<Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} interactive />)
    const props = boardMock.mock.calls[0][0]
    expect(props.arePiecesDraggable).toBe(true)
  })

  it('calls onMove with uci/fen/san on a legal drag/drop', () => {
    const onMove = vi.fn()
    render(
      <Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} interactive onMove={onMove} />,
    )
    const props = boardMock.mock.calls[0][0]
    let handled = false
    act(() => {
      handled = props.onPieceDrop('e2', 'e4')
    })
    expect(handled).toBe(true)
    expect(onMove).toHaveBeenCalledWith({
      uci: 'e2e4',
      fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
      san: 'e4',
    })
  })

  it('does not call onMove and returns false on an illegal drag/drop', () => {
    const onMove = vi.fn()
    render(
      <Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} interactive onMove={onMove} />,
    )
    const props = boardMock.mock.calls[0][0]
    let handled = true
    act(() => {
      handled = props.onPieceDrop('e2', 'e5')
    })
    expect(handled).toBe(false)
    expect(onMove).not.toHaveBeenCalled()
  })

  it('does not wire up move handling when interactive is false', () => {
    const onMove = vi.fn()
    render(<Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} onMove={onMove} />)
    const props = boardMock.mock.calls[0][0]
    let handled = true
    act(() => {
      handled = props.onPieceDrop('e2', 'e4')
    })
    expect(handled).toBe(false)
    expect(onMove).not.toHaveBeenCalled()
  })

  it('selects a square on click, shows legal-move highlights, and completes the move on a second click', () => {
    const onMove = vi.fn()
    render(
      <Chessboard fen={START_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} interactive onMove={onMove} />,
    )
    const initialProps = boardMock.mock.calls[0][0]
    act(() => {
      initialProps.onSquareClick('e2')
    })
    const afterSelectProps = boardMock.mock.calls[boardMock.mock.calls.length - 1][0]
    expect(afterSelectProps.customSquareStyles.e4).toBeDefined()

    act(() => {
      afterSelectProps.onSquareClick('e4')
    })
    expect(onMove).toHaveBeenCalledWith({
      uci: 'e2e4',
      fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
      san: 'e4',
    })
  })

  it('opens a promotion picker on a promotion-shaped drop instead of calling onMove immediately', () => {
    const onMove = vi.fn()
    const PROMOTION_FEN = '4k3/P7/8/8/8/8/8/4K3 w - - 0 1'
    render(
      <Chessboard fen={PROMOTION_FEN} orientation="white" lastmoveFrom={null} lastmoveTo={null} interactive onMove={onMove} />,
    )
    const props = boardMock.mock.calls[0][0]
    act(() => {
      props.onPieceDrop('a7', 'a8')
    })
    expect(onMove).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Promote to Queen' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Promote to Queen' }))
    expect(onMove).toHaveBeenCalledWith({
      uci: 'a7a8q',
      fen: expect.any(String),
      san: expect.stringContaining('=Q'),
    })
  })
})

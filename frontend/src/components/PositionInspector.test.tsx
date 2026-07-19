import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PositionInspector from './PositionInspector'

const { analyseMock, useAnalysePositionMock } = vi.hoisted(() => ({
  analyseMock: vi.fn(),
  useAnalysePositionMock: vi.fn(),
}))
vi.mock('../hooks/useAnalysePosition', () => ({
  useAnalysePosition: () => useAnalysePositionMock(),
}))

vi.mock('./Chessboard', () => ({
  default: (props: { arrows?: Array<{ from: string; to: string; color?: string }> }) => (
    <div data-testid="chessboard" data-arrows={JSON.stringify(props.arrows ?? [])} />
  ),
}))

const FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

describe('PositionInspector', () => {
  it('renders null when fen is null', () => {
    useAnalysePositionMock.mockReturnValue({
      analyse: analyseMock, result: null, resultFen: null, status: 'idle', loading: false,
    })
    const { container } = render(
      <PositionInspector fen={null} flip={false} onFlipToggle={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('calls analyse with the given fen', () => {
    useAnalysePositionMock.mockReturnValue({
      analyse: analyseMock, result: null, resultFen: null, status: 'idle', loading: true,
    })
    render(<PositionInspector fen={FEN} flip={false} onFlipToggle={vi.fn()} />)
    expect(analyseMock).toHaveBeenCalledWith(FEN)
  })

  it('shows a formatted eval and best move once analysis resolves', () => {
    useAnalysePositionMock.mockReturnValue({
      analyse: analyseMock,
      result: { eval_cp: 125, eval_mate: null, best_move_san: 'Nf3', best_move_from: 'g1',
                best_move_to: 'f3', pv: ['Nf3', 'd5'], depth: 18, source: 'stored' },
      resultFen: FEN, status: 'ok', loading: false,
    })
    render(<PositionInspector fen={FEN} flip={false} onFlipToggle={vi.fn()} />)
    expect(screen.getByText(/\+1\.25/)).toBeInTheDocument()
    // 'Nf3' legitimately appears twice (the "Engine best" line and the PV
    // line) -- found live via getByText's ambiguous-match error.
    expect(screen.getAllByText(/Nf3/).length).toBeGreaterThan(0)
  })

  it('draws a green engine arrow and no gold arrow when no playerSan is given', () => {
    useAnalysePositionMock.mockReturnValue({
      analyse: analyseMock,
      result: { eval_cp: 10, eval_mate: null, best_move_san: 'Nf3', best_move_from: 'g1',
                best_move_to: 'f3', pv: [], depth: 10, source: 'stored' },
      resultFen: FEN, status: 'ok', loading: false,
    })
    render(<PositionInspector fen={FEN} flip={false} onFlipToggle={vi.fn()} />)
    const arrows = JSON.parse(screen.getByTestId('chessboard').dataset.arrows ?? '[]')
    expect(arrows).toEqual([{ from: 'g1', to: 'f3', color: 'var(--color-positive)' }])
  })

  it('draws both a gold player arrow and a green engine arrow when they differ', () => {
    useAnalysePositionMock.mockReturnValue({
      analyse: analyseMock,
      result: { eval_cp: 10, eval_mate: null, best_move_san: 'Nf3', best_move_from: 'g1',
                best_move_to: 'f3', pv: [], depth: 10, source: 'stored' },
      resultFen: FEN, status: 'ok', loading: false,
    })
    // FEN is black-to-move after 1.e4 -- 'd4' is illegal here (found live:
    // resolveArrow correctly returned null for it); 'd5' is the legal
    // reply that differs from the engine's 'Nf3'.
    render(<PositionInspector fen={FEN} playerSan="d5" flip={false} onFlipToggle={vi.fn()} />)
    const arrows = JSON.parse(screen.getByTestId('chessboard').dataset.arrows ?? '[]')
    expect(arrows).toHaveLength(2)
  })
})

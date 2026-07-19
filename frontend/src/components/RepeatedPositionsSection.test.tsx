import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RepeatedPositionsSection from './RepeatedPositionsSection'

const mockUseRepeatedPositions = vi.fn()
vi.mock('../hooks/useRepeatedPositions', () => ({ useRepeatedPositions: () => mockUseRepeatedPositions() }))

const mockUsePositionFen = vi.fn()
// Forwards args (unlike a bare `() => mockUsePositionFen()`) -- found live:
// without forwarding, toHaveBeenCalledWith(ply, zobristHash) assertions
// below always see an empty call-args array and fail.
vi.mock('../hooks/usePositionFen', () => ({
  usePositionFen: (...args: unknown[]) => mockUsePositionFen(...args),
}))

vi.mock('./PositionInspector', () => ({
  default: (props: { fen: string | null }) => <div data-testid="inspector" data-fen={props.fen ?? ''} />,
}))

function position(overrides = {}) {
  return {
    ply: 4, zobrist_hash: '111', n_games: 8, win_pct: 50, draw_pct: 25, loss_pct: 25,
    common_opening: 'Sicilian Defense', ...overrides,
  }
}

describe('RepeatedPositionsSection', () => {
  beforeEach(() => {
    mockUsePositionFen.mockReturnValue({ fen: null, loading: false, error: false })
  })

  it('renders null while loading', () => {
    mockUseRepeatedPositions.mockReturnValue({ positions: null, loading: true, error: false })
    const { container } = render(<RepeatedPositionsSection />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows no PositionInspector fen until a row is selected', () => {
    mockUseRepeatedPositions.mockReturnValue({ positions: [position()], loading: false, error: false })
    render(<RepeatedPositionsSection />)
    expect(mockUsePositionFen).toHaveBeenCalledWith(null, null)
  })

  it('selecting a row requests the fen for that ply/zobrist_hash', () => {
    mockUseRepeatedPositions.mockReturnValue({
      positions: [position(), position({ ply: 8, zobrist_hash: '222' })], loading: false, error: false,
    })
    render(<RepeatedPositionsSection />)
    fireEvent.click(screen.getAllByText(/Sicilian Defense/)[0])
    expect(mockUsePositionFen).toHaveBeenLastCalledWith(4, '111')
  })

  it('ArrowDown moves the selection to the next row', () => {
    mockUseRepeatedPositions.mockReturnValue({
      positions: [position(), position({ ply: 8, zobrist_hash: '222' })], loading: false, error: false,
    })
    render(<RepeatedPositionsSection />)
    fireEvent.click(screen.getAllByText(/Sicilian Defense/)[0])
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    expect(mockUsePositionFen).toHaveBeenLastCalledWith(8, '222')
  })
})

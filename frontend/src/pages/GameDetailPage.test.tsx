import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GameDetailPage from './GameDetailPage'

const { boardMock } = vi.hoisted(() => ({ boardMock: vi.fn() }))

vi.mock('react-chessboard', () => ({
  Chessboard: (props: unknown) => {
    boardMock(props)
    return <div data-testid="board" />
  },
}))
vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plot" />,
}))

const mockUseGameDetail = vi.fn()
vi.mock('../hooks/useGameDetail', () => ({
  useGameDetail: (gameId: string | null) => mockUseGameDetail(gameId),
}))

const mockUseAnalysePosition = vi.fn()
vi.mock('../hooks/useAnalysePosition', () => ({
  useAnalysePosition: () => mockUseAnalysePosition(),
}))

const mockUseVariation = vi.fn()
vi.mock('../hooks/useVariation', () => ({
  useVariation: (gameId: string, onMutated?: () => void) => mockUseVariation(gameId, onMutated),
}))

const mockUseSavedVariations = vi.fn()
vi.mock('../hooks/useSavedVariations', () => ({
  useSavedVariations: (gameId: string | null) => mockUseSavedVariations(gameId),
}))

const mockUseClaudeKeyStatus = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({
  useClaudeKeyStatus: () => mockUseClaudeKeyStatus(),
}))

const mockUseProStatus = vi.fn()
vi.mock('../hooks/useProStatus', () => ({
  useProStatus: () => mockUseProStatus(),
}))

const mockUseGameReport = vi.fn()
vi.mock('../hooks/useGameReport', () => ({
  useGameReport: (gameId: string | null) => mockUseGameReport(gameId),
}))

const mockUseBoardChat = vi.fn()
vi.mock('../hooks/useBoardChat', () => ({
  useBoardChat: (gameId: string) => mockUseBoardChat(gameId),
}))

const mockUseGameAnnotation = vi.fn()
vi.mock('../hooks/useGameAnnotation', () => ({
  useGameAnnotation: (gameId: string, ply: number | null, fen: string | null) =>
    mockUseGameAnnotation(gameId, ply, fen),
}))

const mockUseVariationAnnotation = vi.fn()
vi.mock('../hooks/useVariationAnnotation', () => ({
  useVariationAnnotation: (variationId: string | null, step: number, fen: string | null) =>
    mockUseVariationAnnotation(variationId, step, fen),
}))

const HEADER = {
  game_id: 'abc123', utc_date: '2026-01-01', opponent_name: 'kingslayer99', opponent_rating: 1500,
  player_rating: 1520, player_color: 'white' as const, outcome_for_player: 'win' as const,
  time_control_category: 'blitz', opening_family: 'Sicilian Defense', rating_diff: 20,
  game_end_type: 'checkmate', analysis_status: 'done', last_analyzed_ply: 2,
  site: 'https://lichess.org/abc123', lichess_url: 'https://lichess.org/abc123',
  is_comeback: true, is_giant_killing: false, is_brilliant_find: false,
  is_blunder_fest: false, is_nail_biter: false,
}

const MOVES = [
  { ply: 1, san: 'e4', is_player_move: 1, classification: 'good', cpl: 0, sharpness: 0.1,
    is_brilliant_candidate: false, is_puzzle_trigger: false,
    fen_before: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    fen_after: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
    win_prob_before: 0.5, win_prob_after: 0.55, motif: null },
  { ply: 2, san: 'e5', is_player_move: 0, classification: 'good', cpl: 0, sharpness: 0.1,
    is_brilliant_candidate: false, is_puzzle_trigger: false,
    fen_before: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
    fen_after: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2',
    win_prob_before: 0.45, win_prob_after: 0.6, motif: null },
]

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/game-explorer/abc123']}>
      <Routes>
        <Route path="/game-explorer/:gameId" element={<GameDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('GameDetailPage', () => {
  beforeEach(() => {
    mockUseAnalysePosition.mockReturnValue({
      analyse: vi.fn(), result: null, status: 'idle', loading: false,
    })
    mockUseVariation.mockReturnValue({
      active: false, variationId: null, branchPly: null, moves: [], sans: [], step: 0,
      currentFen: null, lastMoveSquares: null,
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(), load: vi.fn(),
    })
    mockUseSavedVariations.mockReturnValue({ variations: [], loading: false, refetch: vi.fn() })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameAnnotation.mockReturnValue({
      annotation: null, loading: false, save: vi.fn(), saveError: null,
      askClaude: vi.fn(), aiLoading: false, aiError: null,
    })
    mockUseVariationAnnotation.mockReturnValue({
      annotation: null, loading: false, save: vi.fn(), saveError: null,
      askClaude: vi.fn(), aiLoading: false, aiError: null,
    })
    mockUseProStatus.mockReturnValue({ active: false, loading: false })
    mockUseGameReport.mockReturnValue({
      reportText: null, generatedAt: null, loading: false,
      generate: vi.fn(), generating: false, error: null, errorStatus: null,
    })
    mockUseBoardChat.mockReturnValue({
      displayHistory: [], conversationId: null, sending: false, error: null,
      pastConversations: [], arrows: [], highlights: {},
      sendMessage: vi.fn(), loadPastConversations: vi.fn(),
      resumeConversation: vi.fn(), sendFeedback: vi.fn(),
    })
  })

  it('shows a loading state', () => {
    mockUseGameDetail.mockReturnValue({
      header: null, moves: null, winProb: null, loading: true, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows a not-found message', () => {
    mockUseGameDetail.mockReturnValue({
      header: null, moves: null, winProb: null, loading: false, error: false, notFound: true,
    })
    renderPage()
    expect(screen.getByText(/couldn't be found/)).toBeInTheDocument()
  })

  it('renders the header, badge chips, board, move list, and eval graph', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText(/kingslayer99/)).toBeInTheDocument()
    expect(screen.getByText('Comeback')).toBeInTheDocument()
    expect(screen.getByTestId('board')).toBeInTheDocument()
    expect(screen.getByText('1. e4')).toBeInTheDocument()
    expect(screen.getByTestId('plot')).toBeInTheDocument()
  })

  it('defaults ply to the last move once moves load', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText('e5').className).toContain('text-[var(--cw-copper)]')
  })

  it('moves the highlighted ply when a move-list entry is clicked', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    fireEvent.click(screen.getByText('1. e4'))
    expect(screen.getByText('1. e4').className).toContain('text-[var(--cw-copper)]')
    expect(screen.getByText('e5').className).not.toContain('text-[var(--cw-copper)]')
  })

  it('shows an Analyse position button that calls analyse() with the current FEN', () => {
    const analyse = vi.fn()
    mockUseAnalysePosition.mockReturnValue({ analyse, result: null, status: 'idle', loading: false })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Analyse position' }))
    expect(analyse).toHaveBeenCalledWith(MOVES[1].fen_after)
  })

  it('renders eval/PV/depth on a successful analysis', () => {
    mockUseAnalysePosition.mockReturnValue({
      analyse: vi.fn(),
      result: {
        eval_cp: 40, eval_mate: null, best_move_san: 'Nf6', best_move_from: 'g8', best_move_to: 'f6',
        pv: ['Nf6', 'Nc3'], depth: 22, source: 'live',
      },
      status: 'ok',
      loading: false,
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText(/Nf6/)).toBeInTheDocument()
    expect(screen.getByText(/depth 22/)).toBeInTheDocument()
  })

  it('draws the engine best-move arrow on the board after a successful analysis', () => {
    mockUseAnalysePosition.mockReturnValue({
      analyse: vi.fn(),
      result: {
        eval_cp: 40, eval_mate: null, best_move_san: 'Nf6', best_move_from: 'g8', best_move_to: 'f6',
        pv: ['Nf6'], depth: 22, source: 'live',
      },
      status: 'ok',
      loading: false,
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    const lastCallProps = boardMock.mock.calls[boardMock.mock.calls.length - 1][0]
    expect(lastCallProps.customArrows).toEqual([['g8', 'f6', 'var(--color-positive)']])
  })

  it.each([
    ['no_engine', /Stockfish not found/],
    ['batch_running', /Batch analysis running/],
    ['analysis_failed', /couldn't be analysed/],
  ])('shows the right message for status %s', (status, expectedText) => {
    mockUseAnalysePosition.mockReturnValue({ analyse: vi.fn(), result: null, status, loading: false })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText(expectedText)).toBeInTheDocument()
  })

  it('disables the button while loading', () => {
    mockUseAnalysePosition.mockReturnValue({ analyse: vi.fn(), result: null, status: 'idle', loading: true })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByRole('button', { name: 'Analyse position' })).toBeDisabled()
  })

  it('dragging a legal move on the mainline board calls variation.applyMove', () => {
    const applyMove = vi.fn()
    mockUseVariation.mockReturnValue({
      active: false, variationId: null, branchPly: null, moves: [], sans: [], step: 0,
      currentFen: null, lastMoveSquares: null,
      applyMove, stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    const boardProps = boardMock.mock.calls[boardMock.mock.calls.length - 1][0]
    act(() => {
      boardProps.onPieceDrop('g1', 'f3')
    })
    expect(applyMove).toHaveBeenCalledWith(2, MOVES[1].fen_after, { uci: 'g1f3', fen: expect.any(String), san: 'Nf3' })
  })

  it('shows the VariationPanel once a variation is active', () => {
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g1f3'], sans: ['Nf3'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText('Variation from move 1 — 1 of 1 moves')).toBeInTheDocument()
  })

  it('exits the variation when a mainline move-list entry is clicked', () => {
    const exit = vi.fn()
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g1f3'], sans: ['Nf3'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo: vi.fn(), exit, discard: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    fireEvent.click(screen.getByText('1. e4'))
    expect(exit).toHaveBeenCalled()
  })

  it('steps the variation (not mainline ply) on arrow keys while active', () => {
    const stepTo = vi.fn()
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g1f3', 'b8c6'], sans: ['Nf3', 'Nc6'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo, exit: vi.fn(), discard: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(stepTo).toHaveBeenCalledWith(2)
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(stepTo).toHaveBeenCalledWith(0)
  })

  it('calls variation.discard from the VariationPanel Discard button', () => {
    const discard = vi.fn()
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g1f3'], sans: ['Nf3'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard,
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Discard variation' }))
    expect(discard).toHaveBeenCalled()
  })

  it('passes the saved-variations refetch as the onMutated callback to useVariation', () => {
    const refetch = vi.fn()
    mockUseSavedVariations.mockReturnValue({ variations: [], loading: false, refetch })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(mockUseVariation).toHaveBeenCalledWith('abc123', refetch)
  })

  it('renders SavedVariationsPanel rows and wires Load to useVariation.load', () => {
    const load = vi.fn()
    mockUseSavedVariations.mockReturnValue({
      variations: [{
        id: 'v1', game_id: 'abc123', branch_ply: 2,
        branch_fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
        moves: ['g8f6'], title: null, created_at: '2026-01-01', updated_at: '2026-01-01',
      }],
      loading: false,
      refetch: vi.fn(),
    })
    mockUseVariation.mockReturnValue({
      active: false, variationId: null, branchPly: null, moves: [], sans: [], step: 0,
      currentFen: null, lastMoveSquares: null,
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(), load,
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()

    expect(screen.getByText(/From move 1/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Load' }))
    expect(load).toHaveBeenCalledWith(expect.objectContaining({ id: 'v1' }))
  })

  it('deletes a saved variation, refetches the list, and resets the active variation if it matched', async () => {
    const refetch = vi.fn()
    const exit = vi.fn()
    mockUseSavedVariations.mockReturnValue({
      variations: [{
        id: 'v1', game_id: 'abc123', branch_ply: 2,
        branch_fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
        moves: ['g8f6'], title: null, created_at: '2026-01-01', updated_at: '2026-01-01',
      }],
      loading: false,
      refetch,
    })
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g8f6'], sans: ['Nf6'], step: 1,
      currentFen: 'fen-after', lastMoveSquares: null,
      applyMove: vi.fn(), stepTo: vi.fn(), exit, discard: vi.fn(), load: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true })))

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(refetch).toHaveBeenCalled())
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/variations/v1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(exit).toHaveBeenCalled()

    vi.unstubAllGlobals()
  })

  it('always renders the mainline AnnotationPanel once a ply is set', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getByText('Annotate this position')).toBeInTheDocument()
    expect(mockUseGameAnnotation).toHaveBeenCalledWith('abc123', 2, MOVES[1].fen_after)
  })

  it('does not render a variation AnnotationPanel when no variation is active', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    // Exactly one AnnotationPanel (the mainline one) is rendered.
    expect(screen.getAllByText('Annotate this position')).toHaveLength(1)
  })

  it('does not render a variation AnnotationPanel while variationId is still null', () => {
    mockUseVariation.mockReturnValue({
      active: true, variationId: null, branchPly: 2, moves: ['g1f3'], sans: ['Nf3'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getAllByText('Annotate this position')).toHaveLength(1)
  })

  it('renders a second AnnotationPanel for the active variation once variationId is set', () => {
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g1f3'], sans: ['Nf3'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(),
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()
    expect(screen.getAllByText('Annotate this position')).toHaveLength(2)
    expect(mockUseVariationAnnotation).toHaveBeenCalledWith('v1', 1, 'SOME_FEN')
  })

  it('gates evalCp/bestMoveSan on resultFen matching the position being annotated', () => {
    mockUseAnalysePosition.mockReturnValue({
      analyse: vi.fn(),
      result: { eval_cp: 40, eval_mate: null, best_move_san: 'Nf6', best_move_from: 'g8', best_move_to: 'f6', pv: [], depth: 20, source: 'live' },
      resultFen: 'SOME_OTHER_FEN', // does not match mainlineFen (MOVES[1].fen_after)
      status: 'ok',
      loading: false,
    })
    const askClaude = vi.fn()
    mockUseGameAnnotation.mockReturnValue({
      annotation: null, loading: false, save: vi.fn(), saveError: null,
      askClaude, aiLoading: false, aiError: null,
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Ask Claude to comment' }))
    expect(askClaude).toHaveBeenCalledWith(null, null, null)
  })

  it('passes evalCp/bestMoveSan through when resultFen matches the position being annotated', () => {
    mockUseAnalysePosition.mockReturnValue({
      analyse: vi.fn(),
      result: { eval_cp: 40, eval_mate: null, best_move_san: 'Nf6', best_move_from: 'g8', best_move_to: 'f6', pv: [], depth: 20, source: 'live' },
      resultFen: MOVES[1].fen_after,
      status: 'ok',
      loading: false,
    })
    const askClaude = vi.fn()
    mockUseGameAnnotation.mockReturnValue({
      annotation: null, loading: false, save: vi.fn(), saveError: null,
      askClaude, aiLoading: false, aiError: null,
    })
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES,
      winProb: [{ ply: 1, player_win_prob: 0.55 }, { ply: 2, player_win_prob: 0.4 }],
      loading: false, error: false, notFound: false,
    })
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Ask Claude to comment' }))
    expect(askClaude).toHaveBeenCalledWith(40, 'Nf6', null)
  })

  it('mounts GameReportPanel once in mainline mode', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [], loading: false, error: false, notFound: false,
    })

    renderPage()

    // GameReportPanel's own top label ("Game Report") collides with
    // ProUpsell's "Game Report" bold text when Pro is inactive (the
    // beforeEach default) -- assert on the panel's always-rendered,
    // unique description text instead.
    expect(screen.getByText(/A structured coach's review/)).toBeInTheDocument()
  })

  it('does not mount GameReportPanel in variation mode', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [], loading: false, error: false, notFound: false,
    })
    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 2, moves: ['g1f3'], sans: ['Nf3'], step: 1,
      currentFen: 'SOME_FEN', lastMoveSquares: { from: 'g1', to: 'f3' },
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(), load: vi.fn(),
    })

    renderPage()

    expect(screen.queryByText(/A structured coach's review/)).not.toBeInTheDocument()
  })

  it('mounts BoardChatPanel once in both mainline and variation mode', () => {
    // "Board Chat" collides with ProUpsell's own bold "Board Chat" text when
    // Pro is inactive (the beforeEach default) -- same collision class as
    // GameReportPanel/"Game Report" above; assert on the panel's
    // always-rendered, unique description text instead.
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [], loading: false, error: false, notFound: false,
    })
    const { unmount } = renderPage()
    expect(screen.getByText(/it can draw arrows and highlight squares/)).toBeInTheDocument()
    unmount()

    mockUseVariation.mockReturnValue({
      active: true, variationId: 'v1', branchPly: 1, moves: [], sans: [], step: 0,
      currentFen: 'variation-fen', lastMoveSquares: null,
      applyMove: vi.fn(), stepTo: vi.fn(), exit: vi.fn(), discard: vi.fn(), load: vi.fn(),
    })
    renderPage()
    expect(screen.getAllByText(/it can draw arrows and highlight squares/)).toHaveLength(1)
  })

  it('concatenates engine-analysis arrows with Board Chat arrows on the Chessboard mount', () => {
    mockUseGameDetail.mockReturnValue({
      header: HEADER, moves: MOVES, winProb: [], loading: false, error: false, notFound: false,
    })
    mockUseAnalysePosition.mockReturnValue({
      analyse: vi.fn(),
      result: { best_move_from: 'e2', best_move_to: 'e4', best_move_san: 'e4', eval_cp: 30, eval_mate: null, pv: [], depth: 20 },
      resultFen: MOVES[1].fen_after,
      status: 'ok',
      loading: false,
    })
    mockUseBoardChat.mockReturnValue({
      displayHistory: [], conversationId: null, sending: false, error: null,
      pastConversations: [], arrows: [{ from: 'g1', to: 'f3', color: '#6FA98C' }], highlights: {},
      sendMessage: vi.fn(), loadPastConversations: vi.fn(),
      resumeConversation: vi.fn(), sendFeedback: vi.fn(),
    })
    renderPage()
    // boardMock records the mocked react-chessboard library component's own
    // props, not our Chessboard.tsx wrapper's -- the wrapper maps its
    // `arrows` prop to the library's `customArrows` tuple shape before
    // rendering it, same conversion `boardMock.customArrows` assertions
    // elsewhere in this file already check.
    const lastCallProps = boardMock.mock.calls[boardMock.mock.calls.length - 1][0]
    expect(lastCallProps.customArrows).toEqual([
      ['e2', 'e4', 'var(--color-positive)'],
      ['g1', 'f3', '#6FA98C'],
    ])
  })
})

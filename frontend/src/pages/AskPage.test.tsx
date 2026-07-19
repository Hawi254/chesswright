import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AskPage from './AskPage'

const useAskStreamMock = vi.fn()
vi.mock('../hooks/useAskStream', () => ({ useAskStream: () => useAskStreamMock() }))

const useClaudeKeyStatusMock = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({ useClaudeKeyStatus: () => useClaudeKeyStatusMock() }))

function stubHeadlineStats(analyzedGames: number) {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
    ok: true,
    json: async () => ({ analyzed_games: analyzedGames }),
  })))
}

const NO_CARDS = { cards: [], ask: vi.fn(), retry: vi.fn(), clearHistory: vi.fn() }

describe('AskPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('shows the thin-data gate when there are no analyzed games, hiding the input zone', async () => {
    stubHeadlineStats(0)
    useClaudeKeyStatusMock.mockReturnValue({ available: true })
    useAskStreamMock.mockReturnValue(NO_CARDS)

    render(<AskPage />)

    await waitFor(() => expect(screen.getByText(/Not enough data yet/)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Blunder timing' })).not.toBeInTheDocument()
  })

  it('shows the missing-Claude-key gate when there are analyzed games but no key', async () => {
    stubHeadlineStats(50)
    useClaudeKeyStatusMock.mockReturnValue({ available: false })
    useAskStreamMock.mockReturnValue(NO_CARDS)

    render(<AskPage />)

    await waitFor(() => expect(screen.getByText(/Add your own Anthropic API key/)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Blunder timing' })).not.toBeInTheDocument()
  })

  it('submits the full preset question text when a chip is clicked', async () => {
    stubHeadlineStats(50)
    useClaudeKeyStatusMock.mockReturnValue({ available: true })
    const ask = vi.fn()
    useAskStreamMock.mockReturnValue({ ...NO_CARDS, ask })

    render(<AskPage />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Blunder timing' })).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Blunder timing' }))
    expect(ask).toHaveBeenCalledWith('When do I blunder most — opening, middlegame, or endgame?')
  })

  it('submits the free-text question when Ask is clicked', async () => {
    stubHeadlineStats(50)
    useClaudeKeyStatusMock.mockReturnValue({ available: true })
    const ask = vi.fn()
    useAskStreamMock.mockReturnValue({ ...NO_CARDS, ask })

    render(<AskPage />)

    await waitFor(() => expect(screen.getByPlaceholderText(/blunder most/)).toBeInTheDocument())
    await userEvent.type(screen.getByPlaceholderText(/blunder most/), 'Custom question?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(ask).toHaveBeenCalledWith('Custom question?')
  })

  it('shows the single-turn caption before any card exists, and Clear history once one does', async () => {
    stubHeadlineStats(50)
    useClaudeKeyStatusMock.mockReturnValue({ available: true })
    useAskStreamMock.mockReturnValue({
      cards: [{ id: 'c1', question: 'Q', answer: 'A', status: 'settled', errorMessage: null, askedAt: new Date().toISOString() }],
      ask: vi.fn(), retry: vi.fn(), clearHistory: vi.fn(),
    })

    render(<AskPage />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Clear history' })).toBeInTheDocument())
    expect(screen.queryByText(/won't remember earlier questions/)).not.toBeInTheDocument()
    expect(screen.getByText('Q')).toBeInTheDocument()
  })
})

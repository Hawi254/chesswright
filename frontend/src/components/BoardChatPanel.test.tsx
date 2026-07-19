import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BoardChatPanel from './BoardChatPanel'

const mockUseProStatus = vi.fn()
vi.mock('../hooks/useProStatus', () => ({
  useProStatus: () => mockUseProStatus(),
}))

const mockUseClaudeKeyStatus = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({
  useClaudeKeyStatus: () => mockUseClaudeKeyStatus(),
}))

function baseProps(overrides = {}) {
  return {
    gameId: 'g1',
    currentFen: 'startpos-fen',
    displayHistory: [],
    conversationId: null,
    sending: false,
    error: null,
    pastConversations: [],
    sendMessage: vi.fn(),
    loadPastConversations: vi.fn(),
    resumeConversation: vi.fn(),
    sendFeedback: vi.fn(),
    ...overrides,
  }
}

describe('BoardChatPanel', () => {
  it('renders nothing extra while pro-status is loading', () => {
    mockUseProStatus.mockReturnValue({ active: false, loading: true })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    render(<BoardChatPanel {...baseProps()} />)
    expect(screen.queryByText(/Chesswright Pro feature/)).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/best move here/)).not.toBeInTheDocument()
  })

  it('shows the upsell when Pro is not active', () => {
    mockUseProStatus.mockReturnValue({ active: false, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    render(<BoardChatPanel {...baseProps()} />)
    expect(screen.getByText(/Chesswright Pro feature/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /chesswright.gumroad.com/ })).toHaveAttribute(
      'href', 'https://chesswright.gumroad.com',
    )
  })

  it('shows the missing-API-key message when Pro is active but no key is configured', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: false })
    render(<BoardChatPanel {...baseProps()} />)
    expect(screen.getByText(/Add your own Anthropic API key on the Settings page/)).toBeInTheDocument()
  })

  it('shows the chat input and Send button when both gates pass', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    render(<BoardChatPanel {...baseProps()} />)
    expect(screen.getByPlaceholderText(/best move here/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })

  it('shows the past-conversations list only before the first message, and calls resumeConversation', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    const resumeConversation = vi.fn()
    render(<BoardChatPanel {...baseProps({
      pastConversations: [{ id: 7, started_at: '2026-07-10', turn_count: 3 }],
      resumeConversation,
    })} />)
    expect(screen.getByText(/1 past conversation for this game/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
    expect(resumeConversation).toHaveBeenCalledWith(7, 'startpos-fen')
  })

  it('hides the past-conversations list once a conversation is underway', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    render(<BoardChatPanel {...baseProps({
      pastConversations: [{ id: 7, started_at: '2026-07-10', turn_count: 3 }],
      conversationId: 7,
      displayHistory: [{ role: 'assistant', content: 'Nf3.', turnId: 5 }],
    })} />)
    expect(screen.queryByText(/past conversation/)).not.toBeInTheDocument()
  })

  it('thumbs buttons call sendFeedback with the right turnId and feedback value', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    const sendFeedback = vi.fn()
    render(<BoardChatPanel {...baseProps({
      displayHistory: [
        { role: 'user', content: 'best move?', turnId: null },
        { role: 'assistant', content: 'Nf3.', turnId: 42 },
      ],
      sendFeedback,
    })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Thumbs up' }))
    expect(sendFeedback).toHaveBeenCalledWith(42, 1)
    fireEvent.click(screen.getByRole('button', { name: 'Thumbs down' }))
    expect(sendFeedback).toHaveBeenCalledWith(42, -1)
  })

  it('disables Send while empty, enables once typed, and swaps label while sending', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    const sendMessage = vi.fn()
    const { rerender } = render(<BoardChatPanel {...baseProps({ sendMessage })} />)
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText(/best move here/), { target: { value: 'what now?' } })
    expect(screen.getByRole('button', { name: 'Send' })).not.toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(sendMessage).toHaveBeenCalledWith('what now?', 'startpos-fen')

    rerender(<BoardChatPanel {...baseProps({ sendMessage, sending: true })} />)
    expect(screen.getByRole('button', { name: 'Claude is thinking…' })).toBeDisabled()
  })

  it('shows inline error text on failure', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    render(<BoardChatPanel {...baseProps({ error: 'Claude API call failed: connection reset' })} />)
    expect(screen.getByText('Claude API call failed: connection reset')).toBeInTheDocument()
  })
})

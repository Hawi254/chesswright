import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScoutingNotesTab from './ScoutingNotesTab'

vi.mock('react-markdown', () => ({ default: ({ children }: { children: string }) => <div>{children}</div> }))

const mockUseOpponentPrepNotes = vi.fn()
vi.mock('../hooks/useOpponentPrepNotes', () => ({
  useOpponentPrepNotes: () => mockUseOpponentPrepNotes(),
}))

const mockUseClaudeKeyStatus = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({
  useClaudeKeyStatus: () => mockUseClaudeKeyStatus(),
}))

describe('ScoutingNotesTab', () => {
  it('shows the missing-API-key message when no key is configured', () => {
    mockUseClaudeKeyStatus.mockReturnValue({ available: false })
    mockUseOpponentPrepNotes.mockReturnValue({
      narrative: null, generatedAt: null, generating: false, generateError: null, generate: vi.fn(),
    })
    render(<ScoutingNotesTab username="DrNykterstein" />)
    expect(screen.getByText(/Add your.*API key.*Settings/i)).toBeInTheDocument()
  })

  it('renders cached narrative and a regenerate button when a key is available', () => {
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseOpponentPrepNotes.mockReturnValue({
      narrative: 'Cached notes', generatedAt: '2026-07-16', generating: false, generateError: null, generate: vi.fn(),
    })
    render(<ScoutingNotesTab username="DrNykterstein" />)
    expect(screen.getByText('Cached notes')).toBeInTheDocument()
    expect(screen.getByText(/Regenerate/i)).toBeInTheDocument()
  })

  it('shows a generate button and no notes yet when nothing is cached', () => {
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseOpponentPrepNotes.mockReturnValue({
      narrative: null, generatedAt: null, generating: false, generateError: null, generate: vi.fn(),
    })
    render(<ScoutingNotesTab username="DrNykterstein" />)
    expect(screen.getByText(/Generate/i)).toBeInTheDocument()
  })
})

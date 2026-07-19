import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import GameReportPanel from './GameReportPanel'

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
}))

const mockUseProStatus = vi.fn()
vi.mock('../hooks/useProStatus', () => ({
  useProStatus: () => mockUseProStatus(),
}))

const mockUseClaudeKeyStatus = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({
  useClaudeKeyStatus: () => mockUseClaudeKeyStatus(),
}))

const mockUseGameReport = vi.fn()
vi.mock('../hooks/useGameReport', () => ({
  useGameReport: (gameId: string | null) => mockUseGameReport(gameId),
}))

function baseGameReport(overrides = {}) {
  return {
    reportText: null,
    generatedAt: null,
    loading: false,
    generate: vi.fn(),
    generating: false,
    error: null,
    errorStatus: null,
    ...overrides,
  }
}

describe('GameReportPanel', () => {
  it('renders nothing extra while pro-status is loading', () => {
    mockUseProStatus.mockReturnValue({ active: false, loading: true })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport())

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.queryByText(/Chesswright Pro feature/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Generate Game Report/)).not.toBeInTheDocument()
  })

  it('shows the upsell when Pro is not active', () => {
    mockUseProStatus.mockReturnValue({ active: false, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport())

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByText(/Chesswright Pro feature/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /chesswright.gumroad.com/ })).toHaveAttribute(
      'href', 'https://chesswright.gumroad.com',
    )
  })

  it('shows the missing-API-key message when Pro is active but no key is configured', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: false })
    mockUseGameReport.mockReturnValue(baseGameReport())

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByText(/Add your Anthropic API key on the Settings page/)).toBeInTheDocument()
  })

  it('shows Generate button and no download links when no report is cached yet', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport())

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByRole('button', { name: 'Generate Game Report' })).toBeInTheDocument()
    expect(screen.queryByText(/Download report/)).not.toBeInTheDocument()
  })

  it('shows the cached report, Regenerate label, and both download links when a report exists', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport({
      reportText: '## Opening\nSolid play.',
      generatedAt: '2026-07-14 10:00',
    }))

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByTestId('markdown')).toHaveTextContent('Solid play.')
    expect(screen.getByText(/Generated 2026-07-14 10:00/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Regenerate report' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download report \(Markdown\)/ })).toHaveAttribute(
      'href', expect.stringContaining('/api/games/g1/report/download.md'),
    )
    expect(screen.getByRole('link', { name: /Download report \(HTML\)/ })).toHaveAttribute(
      'href', expect.stringContaining('/api/games/g1/report/download.html'),
    )
    expect(screen.getByText(/chesswright_report_kingslayer99_2026-07-14\.md/)).toBeInTheDocument()
  })

  it('shows the upsell-style message when generate() fails with 403', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport({ error: 'Pro is not licensed', errorStatus: 403 }))

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByText(/Chesswright Pro feature/)).toBeInTheDocument()
  })

  it("shows the broken-install message when generate() fails with 501", () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport({ error: 'not installed', errorStatus: 501 }))

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByText(/couldn't be imported/)).toBeInTheDocument()
  })

  it('shows inline error text for a 503/502 and keeps the button enabled', () => {
    mockUseProStatus.mockReturnValue({ active: true, loading: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
    mockUseGameReport.mockReturnValue(baseGameReport({
      error: 'No Anthropic API key configured.', errorStatus: 503,
    }))

    render(<GameReportPanel gameId="g1" opponentName="kingslayer99" utcDate="2026-07-14" />)
    expect(screen.getByText('No Anthropic API key configured.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate Game Report' })).not.toBeDisabled()
  })
})

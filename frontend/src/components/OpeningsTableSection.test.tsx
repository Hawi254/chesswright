import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OpeningsTableSection from './OpeningsTableSection'

const mockUseOpeningsTable = vi.fn()
vi.mock('../hooks/useOpeningsTable', () => ({ useOpeningsTable: () => mockUseOpeningsTable() }))

const mockUseOpeningNarrative = vi.fn()
vi.mock('../hooks/useOpeningNarrative', () => ({ useOpeningNarrative: () => mockUseOpeningNarrative() }))

const mockUseClaudeKeyStatus = vi.fn()
vi.mock('../hooks/useClaudeKeyStatus', () => ({ useClaudeKeyStatus: () => mockUseClaudeKeyStatus() }))

function row(overrides = {}) {
  return {
    opening_family: 'Sicilian Defense', player_color: 'white', n: 42,
    win_pct: 55.0, draw_pct: 10.0, acpl: 32.5, n_analyzed: 20, ...overrides,
  }
}

describe('OpeningsTableSection', () => {
  beforeEach(() => {
    mockUseOpeningNarrative.mockReturnValue({
      narrative: null, generatedAt: null, loading: false, error: false,
      generating: false, generateError: null, generate: vi.fn(),
    })
    mockUseClaudeKeyStatus.mockReturnValue({ available: true })
  })

  it('renders null while loading', () => {
    mockUseOpeningsTable.mockReturnValue({ openings: null, loading: true, error: false })
    const { container } = render(<OpeningsTableSection />)
    expect(container).toBeEmptyDOMElement()
  })

  it('sorts by n descending by default', () => {
    mockUseOpeningsTable.mockReturnValue({
      openings: [row({ opening_family: 'Italian Game', n: 5 }), row({ opening_family: 'Sicilian Defense', n: 42 })],
      loading: false, error: false,
    })
    render(<OpeningsTableSection />)
    const cells = screen.getAllByText(/Sicilian Defense|Italian Game/)
    expect(cells[0]).toHaveTextContent('Sicilian Defense')
  })

  it('filters by opening name search', () => {
    mockUseOpeningsTable.mockReturnValue({
      openings: [row({ opening_family: 'Italian Game' }), row({ opening_family: 'Sicilian Defense' })],
      loading: false, error: false,
    })
    render(<OpeningsTableSection />)
    fireEvent.change(screen.getByLabelText(/opening name/i), { target: { value: 'sicilian' } })
    expect(screen.queryByText('Italian Game')).not.toBeInTheDocument()
    expect(screen.getByText('Sicilian Defense')).toBeInTheDocument()
  })

  it('hides rows below the min-games slider threshold', () => {
    mockUseOpeningsTable.mockReturnValue({
      openings: [row({ opening_family: 'Rare Line', n: 2 }), row({ opening_family: 'Sicilian Defense', n: 42 })],
      loading: false, error: false,
    })
    render(<OpeningsTableSection />)
    expect(screen.queryByText('Rare Line')).not.toBeInTheDocument()
  })

  it('shows the ACPL-blank caption when some rows have no analyzed games', () => {
    mockUseOpeningsTable.mockReturnValue({
      openings: [row({ opening_family: 'Sicilian Defense', acpl: null, n_analyzed: 0 })],
      loading: false, error: false,
    })
    render(<OpeningsTableSection />)
    expect(screen.getByText(/ACPL is blank for 1 of 1/)).toBeInTheDocument()
  })

  it('selecting a row shows the detail panel with generate-commentary gating', () => {
    mockUseOpeningsTable.mockReturnValue({ openings: [row()], loading: false, error: false })
    mockUseClaudeKeyStatus.mockReturnValue({ available: false })
    render(<OpeningsTableSection />)
    fireEvent.click(screen.getByText('Sicilian Defense'))
    expect(screen.getByText(/Add your own Anthropic API key/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate commentary/i })).toBeDisabled()
  })

  it('shows Regenerate commentary and the cached text once a narrative exists', () => {
    mockUseOpeningsTable.mockReturnValue({ openings: [row()], loading: false, error: false })
    mockUseOpeningNarrative.mockReturnValue({
      narrative: 'Cached text', generatedAt: '2026-07-14', loading: false, error: false,
      generating: false, generateError: null, generate: vi.fn(),
    })
    render(<OpeningsTableSection />)
    fireEvent.click(screen.getByText('Sicilian Defense'))
    expect(screen.getByText('Cached text')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /regenerate commentary/i })).toBeInTheDocument()
  })
})

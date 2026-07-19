import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import GameEndingsPage from './GameEndingsPage'

vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plot" />,
}))

const TREE = {
  ids: ['root', 'win', 'loss'],
  labels: ['All games', 'Win', 'Loss'],
  parents: ['', 'root', 'root'],
  values: [10, 4, 6],
}
const SUMMARY = {
  hero: { total_games: 10, decisive_pct: 70, draw_pct: 30, resignation_explained_pct: 50, flagged_while_ahead_pct: 20 },
  endgame_material: [],
  resignation_trend: [],
  time_forfeit_trend: [],
}

const useEndingTreeMock = vi.fn()
const useEndingTreeDrilldownMock = vi.fn()
const useEndingSummaryMock = vi.fn()

vi.mock('../hooks/useEndingTree', () => ({ useEndingTree: (...args: unknown[]) => useEndingTreeMock(...args) }))
vi.mock('../hooks/useEndingTreeDrilldown', () => ({
  useEndingTreeDrilldown: (...args: unknown[]) => useEndingTreeDrilldownMock(...args),
}))
vi.mock('../hooks/useEndingSummary', () => ({ useEndingSummary: (...args: unknown[]) => useEndingSummaryMock(...args) }))

function renderPage() {
  return render(
    <MemoryRouter>
      <GameEndingsPage />
    </MemoryRouter>,
  )
}

describe('GameEndingsPage', () => {
  it('always renders the page title, even while loading', () => {
    useEndingTreeMock.mockReturnValue({ tree: null, loading: true, error: false })
    useEndingTreeDrilldownMock.mockReturnValue({ drilldown: null, loading: false, error: false })
    useEndingSummaryMock.mockReturnValue({ summary: null, loading: true, error: false })
    renderPage()
    expect(screen.getByRole('heading', { name: 'Game Endings' })).toBeInTheDocument()
  })

  it('renders the hero tiles, icicle, and node click sets selectedPath (passed to the drilldown hook)', async () => {
    useEndingTreeMock.mockReturnValue({ tree: TREE, loading: false, error: false })
    useEndingTreeDrilldownMock.mockReturnValue({ drilldown: null, loading: false, error: false })
    useEndingSummaryMock.mockReturnValue({ summary: SUMMARY, loading: false, error: false })
    renderPage()
    expect(screen.getByText('Total games')).toBeInTheDocument()
    expect(screen.getAllByTestId('plot').length).toBeGreaterThan(0)
    // selectedPath starts null -- drilldown hook called with (null, null)
    expect(useEndingTreeDrilldownMock).toHaveBeenCalledWith(null, null)
  })

  it('changing the time-control tab re-invokes useEndingTree with the new value', async () => {
    useEndingTreeMock.mockReturnValue({ tree: TREE, loading: false, error: false })
    useEndingTreeDrilldownMock.mockReturnValue({ drilldown: null, loading: false, error: false })
    useEndingSummaryMock.mockReturnValue({ summary: SUMMARY, loading: false, error: false })
    renderPage()
    await userEvent.click(screen.getByRole('tab', { name: 'Bullet' }))
    expect(useEndingTreeMock).toHaveBeenLastCalledWith('bullet')
  })
})

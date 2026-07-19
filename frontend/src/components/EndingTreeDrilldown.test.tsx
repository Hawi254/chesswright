import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EndingTreeDrilldown from './EndingTreeDrilldown'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('EndingTreeDrilldown', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders the breadcrumb and count', () => {
    renderWithRouter(
      <EndingTreeDrilldown
        breadcrumb={{ segments: ['Loss', 'Resignation', 'Hung a piece'], count: 6, pctOfParent: 30 }}
        drilldown={null}
        loading={false}
      />,
    )
    expect(screen.getByText('Loss → Resignation → Hung a piece')).toBeInTheDocument()
    expect(screen.getByText(/6 game\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/30% of its parent/)).toBeInTheDocument()
  })

  it('shows a prompt instead of a game list when nothing is selected', () => {
    renderWithRouter(
      <EndingTreeDrilldown breadcrumb={{ segments: ['All games'], count: 100, pctOfParent: null }} drilldown={null} loading={false} />,
    )
    expect(screen.getByText('Click a segment above to see the games behind it.')).toBeInTheDocument()
  })

  it('renders the capped game list plus a "+N more" note', () => {
    renderWithRouter(
      <EndingTreeDrilldown
        breadcrumb={{ segments: ['Loss', 'Time forfeit'], count: 137, pctOfParent: 20 }}
        drilldown={{ gameIds: ['g1', 'g2'], total: 137, secondaryChart: null, secondaryChartKind: null }}
        loading={false}
      />,
    )
    expect(screen.getByRole('link', { name: 'g1' })).toHaveAttribute('href', '/game-endings/g1')
    expect(screen.getByText('+135 more')).toBeInTheDocument()
  })

  it('renders a secondary chart only when secondaryChart is present', () => {
    renderWithRouter(
      <EndingTreeDrilldown
        breadcrumb={{ segments: ['Loss', 'Resignation', 'Hung a piece'], count: 3, pctOfParent: 50 }}
        drilldown={{
          gameIds: ['g1'], total: 1,
          secondaryChart: [{ label: 'Knight', n: 3, pct: 100 }],
          secondaryChartKind: 'piece',
        }}
        loading={false}
      />,
    )
    expect(plotMock).toHaveBeenCalledTimes(1)
  })

  it('shows a loading state', () => {
    renderWithRouter(
      <EndingTreeDrilldown breadcrumb={{ segments: ['All games'], count: 100, pctOfParent: null }} drilldown={null} loading />,
    )
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })
})

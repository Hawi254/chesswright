import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EndgameMaterialSection from './EndgameMaterialSection'
import type { EndgameMaterialRow } from '../hooks/useEndingSummary'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const ROWS: EndgameMaterialRow[] = [
  { endgame_type: 'Queen', n_games: 10, win_pct: 60, draw_pct: 20, loss_pct: 20, acpl: 30.5, blunder_rate: 4.2 },
  { endgame_type: 'Rook', n_games: 5, win_pct: 40, draw_pct: 40, loss_pct: 20, acpl: null, blunder_rate: null },
]

describe('EndgameMaterialSection', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders a grouped bar chart melted into win/draw/loss long form', () => {
    render(<EndgameMaterialSection rows={ROWS} />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    const chartData = plotMock.mock.calls[0][0].data as Array<{ name: string; y: number[] }>
    const winSeries = chartData.find((s) => s.name === 'win')
    expect(winSeries?.y).toEqual([60, 40])
  })

  it('renders one stat card per endgame type with ACPL and blunder rate', () => {
    render(<EndgameMaterialSection rows={ROWS} />)
    expect(screen.getByText('Queen')).toBeInTheDocument()
    expect(screen.getByText(/30.5/)).toBeInTheDocument()
    expect(screen.getByText(/4.2%/)).toBeInTheDocument()
    expect(screen.getByText('Rook')).toBeInTheDocument()
  })

  it('renders an em dash for null acpl/blunder_rate', () => {
    render(<EndgameMaterialSection rows={ROWS} />)
    const rookCard = screen.getByText('Rook').closest('div')!
    expect(rookCard.textContent).toContain('—')
  })

  it('renders a muted message and no chart for an empty rows list', () => {
    render(<EndgameMaterialSection rows={[]} />)
    expect(screen.getByText('Not enough games yet.')).toBeInTheDocument()
    expect(plotMock).not.toHaveBeenCalled()
  })
})

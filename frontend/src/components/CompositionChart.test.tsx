import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CompositionChart from './CompositionChart'
import type { CompositionShare } from '../hooks/useEvolutionSummary'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const SHARES: CompositionShare[] = [
  { period: 8072, label: '2018 Q1', family: 'Sicilian Defense', n_games: 6, share: 60 },
  { period: 8072, label: '2018 Q1', family: 'Other', n_games: 4, share: 40 },
]

describe('CompositionChart', () => {
  beforeEach(() => {
    plotMock.mockClear()
  })

  it('renders one stacked-bar trace per family with stack barmode', () => {
    render(<CompositionChart shares={SHARES} top={['Sicilian Defense']} />)
    expect(plotMock).toHaveBeenCalledTimes(1)
    const { data, layout } = plotMock.mock.calls[0][0] as {
      data: Array<{ name: string }>
      layout: { barmode: string }
    }
    expect(data.map((t) => t.name)).toEqual(['Sicilian Defense', 'Other'])
    expect(layout.barmode).toBe('stack')
  })

  it('assigns top families the categorical palette in rank order and Other a fixed gray', () => {
    render(<CompositionChart shares={SHARES} top={['Sicilian Defense']} />)
    const { data } = plotMock.mock.calls[0][0] as {
      data: Array<{ name: string; marker: { color: string } }>
    }
    expect(data.find((t) => t.name === 'Sicilian Defense')?.marker.color).toBe('#3987e5')
    expect(data.find((t) => t.name === 'Other')?.marker.color).toBe('#8A8F98')
  })

  it('renders a muted message and no chart for an empty shares list', () => {
    render(<CompositionChart shares={[]} top={[]} />)
    expect(screen.getByText('No games in this range yet.')).toBeInTheDocument()
    expect(plotMock).not.toHaveBeenCalled()
  })
})

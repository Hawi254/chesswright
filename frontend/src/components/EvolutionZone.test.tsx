import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EvolutionZone from './EvolutionZone'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const RATING_TRAJECTORY = [
  { year: 2024, avg_rating: 1400, n_games: 50 },
  { year: 2025, avg_rating: 1500, n_games: 60 },
]

describe('EvolutionZone', () => {
  it('renders the sub-heading and three Plot charts', () => {
    render(
      <EvolutionZone
        ratingTrajectory={RATING_TRAJECTORY}
        acplTrajectory={[
          { year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 },
          { year: 2025, acpl: 42, n_games: 6, n_total_games: 10, coverage_pct: 60 },
        ]}
      />,
    )

    expect(screen.getByText('Rating, accuracy & activity over time')).toBeInTheDocument()
    expect(plotMock).toHaveBeenCalledTimes(3)
  })

  it('passes the rating trajectory data to the first chart in copper', () => {
    render(<EvolutionZone ratingTrajectory={RATING_TRAJECTORY} acplTrajectory={[]} />)

    const [ratingCall] = plotMock.mock.calls.map((c) => c[0])
    expect(ratingCall.data[0].y).toEqual([1400, 1500])
    expect(ratingCall.data[0].line.color).toBe('#E08A3C')
  })

  it('passes games-played volume to the third chart as a muted bar trace', () => {
    render(<EvolutionZone ratingTrajectory={RATING_TRAJECTORY} acplTrajectory={[]} />)

    const volumeCall = plotMock.mock.calls[2][0]
    expect(volumeCall.data[0].type).toBe('bar')
    expect(volumeCall.data[0].y).toEqual([50, 60])
    expect(volumeCall.data[0].marker.color).toBe('rgb(236 238 240 / 0.6)')
  })

  it('shows the coverage warning caption when coverage varies sharply', () => {
    render(
      <EvolutionZone
        ratingTrajectory={[]}
        acplTrajectory={[
          { year: 2024, acpl: 40, n_games: 1, n_total_games: 100, coverage_pct: 1 },
          { year: 2025, acpl: 42, n_games: 50, n_total_games: 100, coverage_pct: 50 },
        ]}
      />,
    )

    expect(screen.getByText(/Analysis coverage varies sharply/)).toBeInTheDocument()
  })

  it('does not show the coverage warning caption when coverage is even', () => {
    render(
      <EvolutionZone
        ratingTrajectory={[]}
        acplTrajectory={[
          { year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 },
          { year: 2025, acpl: 42, n_games: 6, n_total_games: 10, coverage_pct: 60 },
        ]}
      />,
    )

    expect(screen.queryByText(/Analysis coverage varies sharply/)).not.toBeInTheDocument()
  })
})

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import IdentityZone from './IdentityZone'

const STATS = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000, implied_rating: 1973, rating_confidence: 'high' as const,
}
const RATING_SNAPSHOT = { current_rating: 1500, peak_rating: 1550 }
const STREAK = { outcome: 'win', length: 3 }
const FINDINGS = [
  { title: 'Sharp attacker', headline: 'h', detail: 'd', polarity: 'strength' as const,
    severity: 'medium' as const, category: 'tactical' as const },
  { title: 'Time trouble', headline: 'h', detail: 'd', polarity: 'weakness' as const,
    severity: 'high' as const, category: 'time' as const },
]

describe('IdentityZone', () => {
  it('renders stats, rating, streak, narrative, trait tags, and white/black win rate', () => {
    render(
      <IdentityZone
        stats={STATS}
        ratingSnapshot={RATING_SNAPSHOT}
        streak={STREAK}
        findings={FINDINGS}
        narrative="You have played 100 games."
        winRateByColor={[
          { player_color: 'white', n: 60, win_pct: 58.0, draw_pct: 4.0 },
          { player_color: 'black', n: 40, win_pct: 50.4, draw_pct: 3.0 },
        ]}
      />,
    )

    const zone = screen.getByTestId('identity-zone')
    expect(within(zone).getByText('Sharp attacker')).toBeInTheDocument()
    expect(within(zone).getByText('Time trouble')).toBeInTheDocument()
    expect(screen.getByText('1500')).toBeInTheDocument()
    expect(screen.getByText('peak 1550')).toBeInTheDocument()
    expect(screen.getByText(/3-game win streak/)).toBeInTheDocument()
    expect(screen.getByText('You have played 100 games.')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('52.3%')).toBeInTheDocument()
    expect(screen.getByText('45.2')).toBeInTheDocument()
    expect(screen.getByText('58.0%')).toBeInTheDocument()
    expect(screen.getByText('50.4%')).toBeInTheDocument()
  })

  it('shows -- for white/black win rate when winRateByColor is null', () => {
    render(
      <IdentityZone
        stats={STATS}
        ratingSnapshot={RATING_SNAPSHOT}
        streak={STREAK}
        findings={FINDINGS}
        narrative="Narrative."
        winRateByColor={null}
      />,
    )
    expect(screen.getAllByText('--').length).toBeGreaterThanOrEqual(2)
  })

  it('caps trait tags at 3 and prioritizes strengths', () => {
    render(
      <IdentityZone
        stats={{ ...STATS, total_games: 10, analyzed_games: 10 }}
        ratingSnapshot={{ current_rating: 1400, peak_rating: 1400 }}
        streak={{ outcome: null, length: 0 }}
        findings={[
          { title: 'Strength A', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'general' },
          { title: 'Strength B', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'general' },
          { title: 'Weakness A', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'general' },
          { title: 'Weakness B', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'general' },
        ]}
        narrative="Narrative."
        winRateByColor={null}
      />,
    )

    const zone = screen.getByTestId('identity-zone')
    expect(within(zone).getByText('Strength A')).toBeInTheDocument()
    expect(within(zone).getByText('Strength B')).toBeInTheDocument()
    expect(within(zone).getByText('Weakness A')).toBeInTheDocument()
    expect(within(zone).queryByText('Weakness B')).not.toBeInTheDocument()
    expect(screen.getByText('at peak')).toBeInTheDocument()
  })
})

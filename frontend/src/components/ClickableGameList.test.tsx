import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import ClickableGameList from './ClickableGameList'

function renderWithRouter(gameIds: string[], basePath: string) {
  return render(
    <MemoryRouter>
      <ClickableGameList gameIds={gameIds} basePath={basePath} />
    </MemoryRouter>,
  )
}

describe('ClickableGameList', () => {
  it('shows "None." for an empty list', () => {
    renderWithRouter([], 'matchups')
    expect(screen.getByText('None.')).toBeInTheDocument()
  })

  it('renders one link per game id, pointing at /:basePath/:gameId', () => {
    renderWithRouter(['game_1', 'game_2'], 'matchups')
    const link1 = screen.getByRole('link', { name: 'game_1' })
    const link2 = screen.getByRole('link', { name: 'game_2' })
    expect(link1).toHaveAttribute('href', '/matchups/game_1')
    expect(link2).toHaveAttribute('href', '/matchups/game_2')
  })

  it('uses the given basePath for a different caller', () => {
    renderWithRouter(['g1'], 'game-endings')
    expect(screen.getByRole('link', { name: 'g1' })).toHaveAttribute('href', '/game-endings/g1')
  })
})

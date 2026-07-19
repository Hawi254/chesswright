import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EngineStatusStrip from './EngineStatusStrip'
import type { EngineStatusData } from '../hooks/useEngineStatus'

const RESOLVED: EngineStatusData = {
  connected: false, version: null, appVersion: '0.1.25', loading: false, error: false,
}

describe('EngineStatusStrip', () => {
  it('renders nothing while loading', () => {
    const { container } = render(
      <EngineStatusStrip status={{ ...RESOLVED, loading: true }} totalGames={10} analyzedGames={5} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing on error', () => {
    const { container } = render(
      <EngineStatusStrip status={{ ...RESOLVED, error: true }} totalGames={10} analyzedGames={5} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing while total/analyzed game counts are not yet available', () => {
    const { container } = render(
      <EngineStatusStrip status={RESOLVED} totalGames={null} analyzedGames={null} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows "Engine not detected" when not connected', () => {
    render(<EngineStatusStrip status={RESOLVED} totalGames={32295} analyzedGames={4102} />)
    expect(
      screen.getByText('Chesswright v0.1.25 · 32,295 games · 4,102 analyzed · Engine not detected'),
    ).toBeInTheDocument()
  })

  it('shows the Stockfish version when connected', () => {
    render(
      <EngineStatusStrip
        status={{ ...RESOLVED, connected: true, version: '17.1' }}
        totalGames={100}
        analyzedGames={40}
      />,
    )
    expect(
      screen.getByText('Chesswright v0.1.25 · 100 games · 40 analyzed · Stockfish 17.1'),
    ).toBeInTheDocument()
  })
})

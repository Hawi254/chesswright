import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { STATIC_CANDIDATES } from './lib/navCandidates'
import type { OverviewData } from './hooks/useOverviewData'

vi.mock('./hooks/usePageCandidates', () => ({
  usePageCandidates: () => ({ candidates: STATIC_CANDIDATES, usingFallback: false }),
}))

// OverviewPage statically imports EvolutionZone, which statically imports
// react-plotly.js -- that import executes (loading the full plotly.js
// bundle) as soon as this module graph is loaded, even though
// useOverviewData is mocked below to stay in a permanent loading state
// and EvolutionZone never actually renders. The real plotly.js bundle
// touches canvas/WebGL/URL APIs jsdom doesn't implement, so it must be
// mocked here too, same as OverviewPage.test.tsx and
// EvolutionZone.test.tsx already do.
vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plot" />,
}))

const OVERVIEW_LOADING: OverviewData = {
  stats: null, ratingSnapshot: null, streak: null, findings: null, narrative: null,
  loading: true, error: false,
}
vi.mock('./hooks/useOverviewData', () => ({
  useOverviewData: () => OVERVIEW_LOADING,
}))

vi.mock('./hooks/useMatchupsRatingForm', () => ({
  useMatchupsRatingForm: () => ({ data: null, loading: true, error: false }),
}))
vi.mock('./hooks/useNemesisOpponents', () => ({
  useNemesisOpponents: () => ({ rows: null, loading: true, error: false }),
}))
vi.mock('./hooks/usePatternsSummary', () => ({
  usePatternsSummary: () => ({ cards: null, loading: true, error: false }),
}))
vi.mock('./hooks/usePatternsClockTime', () => ({
  usePatternsClockTime: () => ({ data: null, loading: true, error: false }),
}))
vi.mock('./hooks/useEndingTree', () => ({
  useEndingTree: () => ({ tree: null, loading: true, error: false }),
}))
vi.mock('./hooks/useEndingTreeDrilldown', () => ({
  useEndingTreeDrilldown: () => ({ drilldown: null, loading: false, error: false }),
}))
vi.mock('./hooks/useEndingSummary', () => ({
  useEndingSummary: () => ({ summary: null, loading: true, error: false }),
}))
vi.mock('./hooks/useOpponentPrepStatus', () => ({
  useOpponentPrepStatus: () => ({
    data: { status: 'idle', username: null, step: null, error: null },
    loading: false, connectionLost: false,
  }),
}))
vi.mock('./hooks/useOpponentPrepReport', () => ({
  useOpponentPrepReport: () => ({ report: null, loading: false, error: false }),
  useOpponentPrepOpponents: () => ({ opponents: [], loading: false }),
}))
vi.mock('./hooks/useAskStream', () => ({
  useAskStream: () => ({ cards: [], ask: vi.fn(), retry: vi.fn(), clearHistory: vi.fn() }),
}))
vi.mock('./hooks/useClaudeKeyStatus', () => ({
  useClaudeKeyStatus: () => ({ available: false }),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App routing', () => {
  it('redirects / to /overview', () => {
    renderAt('/')
    // OverviewPage no longer renders a literal "Overview" <h1> (dropped
    // per the Engine Room design spec -- the sidebar nav already shows
    // the active page); its loading text is what confirms the redirect
    // landed on the real route rather than a PageStub.
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  // Name is legacy -- /game-endings now renders GameEndingsPage, not
  // PageStub, but PageStub's title text matched GameEndingsPage's <h1>
  // exactly, so this assertion still holds unchanged.
  it('renders the correct stub for a direct URL navigation', () => {
    renderAt('/game-endings')
    expect(screen.getByRole('heading', { name: 'Game Endings' })).toBeInTheDocument()
  })

  it('renders GameEndingsPage (not PageStub) at /game-endings', () => {
    renderAt('/game-endings')
    expect(screen.getByRole('heading', { name: 'Game Endings' })).toBeInTheDocument()
    expect(screen.queryByText('Not yet migrated to the new interface.')).not.toBeInTheDocument()
  })

  it('renders OverviewPage (not PageStub) at /overview', () => {
    renderAt('/overview')
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders MatchupsPage (not PageStub) at /matchups', () => {
    renderAt('/matchups')
    expect(screen.getByRole('heading', { name: 'Matchups & Opponents' })).toBeInTheDocument()
  })

  it('renders PatternsPage (not PageStub) at /patterns', () => {
    renderAt('/patterns')
    expect(screen.getByRole('tab', { name: 'Clock & Time' })).toBeInTheDocument()
  })

  it('renders OpponentPrepPage (not PageStub) at /opponent-prep', () => {
    renderAt('/opponent-prep')
    expect(screen.getByRole('heading', { name: /Opponent Prep/i })).toBeInTheDocument()
    expect(screen.queryByText('Not yet migrated to the new interface.')).not.toBeInTheDocument()
  })

  it('renders AskPage (not PageStub) at /ask', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => ({ analyzed_games: 0 }),
    })))
    renderAt('/ask')
    expect(screen.getByRole('heading', { name: 'Ask about your games' })).toBeInTheDocument()
    expect(screen.queryByText('Not yet migrated to the new interface.')).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InsightsPage from './InsightsPage'

const STATS = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000, implied_rating: 1973, rating_confidence: 'high',
}
const FINDINGS = [
  { title: 'Piece blunder hot-spot', headline: 'Knight moves blunder often', detail: 'd',
    polarity: 'weakness', severity: 'high', category: 'tactical', confidence: 'high', sample_size: 200 },
  { title: 'Clock pressure and blunder rate', headline: 'Blunders spike under 30s', detail: 'd',
    polarity: 'weakness', severity: 'high', category: 'time', confidence: 'high', sample_size: 150 },
  { title: 'Safest piece', headline: 'Rook moves are safe', detail: 'd',
    polarity: 'strength', severity: 'low', category: 'tactical', confidence: 'high', sample_size: 300 },
]
const RATING_SNAPSHOT = { current_rating: 1850, peak_rating: 1920 }

const RESPONSES: Record<string, unknown> = {
  '/api/overview/headline-stats': STATS,
  '/api/overview/career-findings': FINDINGS,
  '/api/overview/rating-snapshot': RATING_SNAPSHOT,
  '/api/overview/headline-trend': {
    compared_to_date: null, acpl_delta: null, blunder_rate_delta: null,
    win_pct_delta: null, implied_rating_delta: null,
  },
  '/api/overview/achievements': [
    { achievement_id: 'first_win', name: 'First Win',
      description: 'Win your first recorded game.', unlocked_at: '2026-01-01T00:00:00' },
  ],
  '/api/insights/synthesis': { narrative: null, generated_at: null },
  '/api/insights/coaching': { narrative: null, generated_at: null },
  '/api/settings/claude-key-status': { available: false },
}

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
  })
}

function renderPage() {
  return render(
    <MemoryRouter>
      <InsightsPage />
    </MemoryRouter>,
  )
}

describe('InsightsPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders every section once data loads', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    renderPage()

    await waitFor(() => expect(screen.getByTestId('performance-summary')).toBeInTheDocument())
    expect(screen.getByTestId('rating-benchmark')).toBeInTheDocument()
    // Hero is the top-severity finding.
    expect(screen.getAllByText('Piece blunder hot-spot').length).toBeGreaterThan(0)
    expect(screen.getByTestId('strengths-column')).toBeInTheDocument()
    expect(screen.getByTestId('weaknesses-column')).toBeInTheDocument()
    // "Tactical" renders repeatedly (hero/critical/strengths/weaknesses/
    // categorized-insights category chips + the category group heading) --
    // getAllByText, not getByText, which throws on more than one match.
    expect(screen.getAllByText('Tactical').length).toBeGreaterThan(0)
    expect(screen.getByText('What your findings add up to')).toBeInTheDocument()
    expect(screen.getByText('What to practice')).toBeInTheDocument()
    expect(screen.getByTestId('recent-improvements')).toBeInTheDocument()
    expect(screen.getByText('First Win')).toBeInTheDocument()
  })

  it('renders the related-finding footer on both critical-findings cards when both paired titles are present', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    renderPage()

    await waitFor(() => expect(screen.getByTestId('performance-summary')).toBeInTheDocument())
    // Both paired findings are severity 'high', so each also renders again
    // (with its own footer) inside "Categorized insights" below -- getAllByText,
    // not getByText, same multiplicity reason as CategorizedInsights.test.tsx.
    expect(screen.getAllByText(/Related: Clock pressure and blunder rate/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Related: Piece blunder hot-spot/).length).toBeGreaterThan(0)
  })

  it('shows a page-level empty state when there are no findings', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/overview/career-findings') return Promise.resolve({ ok: true, json: async () => [] })
      return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
    }))
    renderPage()

    await waitFor(() => expect(screen.getByText(/Nothing to show yet/)).toBeInTheDocument())
    expect(screen.queryByTestId('performance-summary')).not.toBeInTheDocument()
    expect(screen.queryByTestId('rating-benchmark')).not.toBeInTheDocument()
  })

  it('shows an error message when the data request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    renderPage()

    await waitFor(() => expect(screen.getByText(/Couldn't load your Insights data/)).toBeInTheDocument())
  })
})

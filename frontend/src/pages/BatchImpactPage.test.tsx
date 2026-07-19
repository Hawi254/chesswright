import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BatchImpactPage from './BatchImpactPage'
import type { BatchImpactSummary } from '../hooks/useBatchImpact'

vi.mock('react-plotly.js', () => ({ default: () => <div data-testid="plot" /> }))

const SUMMARY: BatchImpactSummary = {
  runs: [
    { id: 2, label: 'Run #2 — 2026-07-02 — 5 games', gamesAnalyzed: 5, endedAt: '2026-07-02' },
    { id: 1, label: 'Run #1 — 2026-07-01 — 5 games', gamesAnalyzed: 5, endedAt: '2026-07-01' },
  ],
  counter: { totalBatches: 2, totalGamesAnalyzed: 10 },
  range: { runA: 1, runB: 2 },
  pendingAnnotation: false,
  headline: {
    gamesInRange: 5, acplBefore: 40, acplAfter: 30, blunderRateBefore: 10, blunderRateAfter: 6,
    newBlunders: 1, newBrilliant: 0, topMotif: 'fork', topMotifCount: 1,
  },
  records: [],
  trend: [
    { runId: 1, endedAt: '2026-07-01', gamesAnalyzed: 5, cumulativeAcpl: 40, cumulativeBlunderRate: 10 },
    { runId: 2, endedAt: '2026-07-02', gamesAnalyzed: 5, cumulativeAcpl: 30, cumulativeBlunderRate: 6 },
  ],
  phase: [],
  endgame: [],
  motifs: [],
  newBlunders: [],
}

describe('BatchImpactPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders the headline once data loads', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><BatchImpactPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Between Run #1 and Run #2')).toBeInTheDocument())
    expect(screen.getByText('40.0 → 30.0')).toBeInTheDocument()
  })

  it('shows the empty-DB message when there are no runs', async () => {
    const empty: BatchImpactSummary = { ...SUMMARY, runs: [], range: { runA: null, runB: null } }
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => empty }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><BatchImpactPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No analysis batches yet/)).toBeInTheDocument())
  })

  it('keeps the EndpointPicker visible and shows the inline hint (not a false load-error) when the user picks the same run twice', async () => {
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: async () => SUMMARY }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><BatchImpactPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Between Run #1 and Run #2')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('To'), { target: { value: '1' } })

    expect(screen.getByText('Pick two different batches to see a diff.')).toBeInTheDocument()
    expect(screen.getByLabelText('From')).toBeInTheDocument()
    expect(screen.getByLabelText('To')).toBeInTheDocument()
    expect(screen.queryByText(/Couldn't load batch impact data/)).not.toBeInTheDocument()
  })
})

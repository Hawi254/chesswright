import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WeaknessesTab from './WeaknessesTab'

const FINDINGS = [
  { title: 'Piece blunder hot-spot', headline: 'h1', detail: 'd1', polarity: 'weakness', severity: 'high', category: 'tactical' },
  { title: 'A strength', headline: 'h2', detail: 'd2', polarity: 'strength', severity: 'high', category: 'tactical' },
]

function stub(motifBackfillNeeded: boolean) {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    if (path === '/api/overview/career-findings') return Promise.resolve({ ok: true, json: async () => FINDINGS })
    if (path === '/api/training/motif-backfill-needed') return Promise.resolve({ ok: true, json: async () => ({ needed: motifBackfillNeeded }) })
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
}

describe('WeaknessesTab', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows only weakness findings, and the motif-backfill banner when needed', async () => {
    vi.stubGlobal('fetch', stub(true))
    render(<MemoryRouter><WeaknessesTab /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Piece blunder hot-spot')).toBeInTheDocument())
    expect(screen.queryByText('A strength')).not.toBeInTheDocument()
    expect(screen.getByText(/Run annotation pass now/i)).toBeInTheDocument()
  })

  it('omits the banner when no motif backfill is needed', async () => {
    vi.stubGlobal('fetch', stub(false))
    render(<MemoryRouter><WeaknessesTab /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Piece blunder hot-spot')).toBeInTheDocument())
    expect(screen.queryByText(/Run annotation pass now/i)).not.toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReviewTab from './ReviewTab'

describe('ReviewTab', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the Pro upsell, relabeled to Review, when Pro is inactive', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/pro-status')) return Promise.resolve({ ok: true, json: async () => ({ active: false }) })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }))
    render(<MemoryRouter><ReviewTab /></MemoryRouter>)
    expect(await screen.findByText(/Chesswright Pro feature/i)).toBeInTheDocument()
    expect(screen.queryByText(/SRS/)).not.toBeInTheDocument()
  })

  it('shows the stats strip when Pro is active', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/pro-status')) return Promise.resolve({ ok: true, json: async () => ({ active: true }) })
      if (url.includes('/api/training/review/stats')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            counts: { total: 10, due: 4, new: 2 },
            weekly_recall: [{ week: '2026-07-13', n_reviews: 5, recall_pct: 80 }],
            learning_curve: [],
            recall_by_source: [{ source: 'Missed Tactics', n_reviews: 10, recall_pct: 70 }],
          }),
        })
      }
      if (url.includes('/api/training/review/due-cards')) return Promise.resolve({ ok: true, json: async () => [] })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }))
    render(<MemoryRouter><ReviewTab /></MemoryRouter>)
    expect(await screen.findByText('4')).toBeInTheDocument()
    expect(screen.getByText('Due today')).toBeInTheDocument()
    expect(screen.getByText('Recall rate')).toBeInTheDocument()
    expect(screen.getByText('70%')).toBeInTheDocument()
    expect(screen.getByText('80% this week')).toBeInTheDocument()
  })
})

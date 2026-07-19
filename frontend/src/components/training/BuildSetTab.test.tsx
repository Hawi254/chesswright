import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BuildSetTab from './BuildSetTab'

function stubPreview(total: number) {
  return vi.fn((url: string) => {
    const u = new URL(url)
    if (u.pathname === '/api/training/build-set/preview') {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          sources: total > 0 ? [{ key: 'missed_tactics', label: 'Missed Tactics', count: total, positions: [] }] : [],
          total,
        }),
      })
    }
    if (u.pathname === '/api/pro-status') return Promise.resolve({ ok: true, json: async () => ({ active: false }) })
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
}

describe('BuildSetTab', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the preview count once the fetch resolves', async () => {
    vi.stubGlobal('fetch', stubPreview(3))
    render(<MemoryRouter><BuildSetTab /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/3 position/)).toBeInTheDocument())
  })

  it('applies a ?preset= from the URL once, then clears it', async () => {
    vi.stubGlobal('fetch', stubPreview(0))
    render(
      <MemoryRouter initialEntries={['/training?tab=build&preset=King moves off the back rank']}>
        <BuildSetTab />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByLabelText('Motif filter')).toHaveValue('back_rank_mate'))
  })

  it('renders download links with the current query params', async () => {
    vi.stubGlobal('fetch', stubPreview(1))
    render(<MemoryRouter><BuildSetTab /></MemoryRouter>)
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /Download Lichess Study PGN/i })
      expect(link).toHaveAttribute('href', expect.stringContaining('/api/training/build-set/download-pgn'))
    })
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OpeningTreePage from './OpeningTreePage'

const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))
vi.mock('react-plotly.js', () => ({ default: (props: unknown) => { plotMock(props); return <div data-testid="plot" /> } }))

function stubProActive(active: boolean) {
  return vi.fn((url: string) => {
    if (url.includes('/api/pro-status')) return Promise.resolve({ ok: true, json: async () => ({ active }) })
    if (url.includes('/api/opening-tree/map')) return Promise.resolve({ ok: true, json: async () => ({ ids: ['root'], labels: ['Start'], parents: [''], values: [0], win_pct: [50], has_flip: [false] }) })
    if (url.includes('/api/opening-tree/moves')) return Promise.resolve({ ok: true, json: async () => [] })
    if (url.includes('/api/opening-tree/changes')) return Promise.resolve({ ok: true, json: async () => [] })
    if (url.includes('/api/openings/table')) return Promise.resolve({ ok: true, json: async () => [] })
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
}

describe('OpeningTreePage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the Pro upsell and fetches no opening-tree data when Pro is inactive', async () => {
    const fetchMock = stubProActive(false)
    vi.stubGlobal('fetch', fetchMock)
    render(<OpeningTreePage />)
    expect(await screen.findByText(/Chesswright Pro feature/i)).toBeInTheDocument()
    expect(screen.queryByTestId('plot')).not.toBeInTheDocument()
    // Both data hooks are called unconditionally (Rules of Hooks) even
    // though the page renders only the upsell -- this asserts they were
    // actually gated from fetching, not just that the fetched data went
    // unrendered (a real live bug: 2026-07-16, three /api/opening-tree/*
    // 403s fired on every load of this exact screen).
    const urls = fetchMock.mock.calls.map((c) => c[0] as string)
    expect(urls.some((u) => u.includes('/api/opening-tree/'))).toBe(false)
  })

  it('renders the canvas (board, icicle, move table) when Pro is active', async () => {
    vi.stubGlobal('fetch', stubProActive(true))
    render(<OpeningTreePage />)
    expect(await screen.findByTestId('plot')).toBeInTheDocument()
    expect(screen.getByText('No games recorded from this position — explore freely on the board.')).toBeInTheDocument()
  })

  it('shows an Add to SRS button targeting the top move once moves load', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/api/pro-status')) return Promise.resolve({ ok: true, json: async () => ({ active: true }) })
      if (url.includes('/api/opening-tree/map')) return Promise.resolve({ ok: true, json: async () => ({ ids: ['root'], labels: ['Start'], parents: [''], values: [10], win_pct: [50], has_flip: [false] }) })
      if (url.includes('/api/opening-tree/moves')) return Promise.resolve({ ok: true, json: async () => [{ san: 'e4', is_player_move: true, n_games: 10, n_wins: 6, n_draws: 2, n_losses: 2, win_pct: 60, draw_pct: 20, loss_pct: 20, avg_cpl: 15 }] })
      if (url.includes('/api/opening-tree/changes')) return Promise.resolve({ ok: true, json: async () => [] })
      if (url.includes('/api/openings/table')) return Promise.resolve({ ok: true, json: async () => [] })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<OpeningTreePage />)

    const addButton = await screen.findByText('Add to SRS deck (e4)')
    fireEvent.click(addButton)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/opening-tree/srs'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('has no back/reset controls at the starting position', async () => {
    vi.stubGlobal('fetch', stubProActive(true))
    render(<OpeningTreePage />)
    await screen.findByTestId('plot')
    expect(screen.queryByText('← Back')).not.toBeInTheDocument()
    expect(screen.queryByText('⌂ Reset')).not.toBeInTheDocument()
  })
})

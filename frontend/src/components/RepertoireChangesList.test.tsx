import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RepertoireChangesList from './RepertoireChangesList'

describe('RepertoireChangesList', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders a row per change with a jump link', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => [{ ply: 3, zobrist_hash: '7', path: ['e4', 'e5', 'Nc3'], before_san: 'Nc3',
        before_share: 100, before_win_pct: 60, before_total: 5, after_san: 'Nf3', after_share: 100,
        after_win_pct: 66.7, after_total: 6 }],
    })))
    const onJumpToPath = vi.fn()
    render(<RepertoireChangesList color="w" minGames={3} onJumpToPath={onJumpToPath} onOpenFlip={vi.fn()} />)

    // Each row's span combines san + win% ("Nc3 (60%)") into one text
    // node group -- getByText needs a partial/regex match, not an exact
    // string, or it won't find either span (same class of gotcha as
    // PositionTimelinePanel's before/after text).
    expect(await screen.findByText(/Nc3/)).toBeInTheDocument()
    expect(screen.getByText(/Nf3/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Jump here'))
    expect(onJumpToPath).toHaveBeenCalledWith(['e4', 'e5', 'Nc3'])
  })

  it('disables "Jump here" for transposition-only rows (path is null)', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: async () => [{ ply: 3, zobrist_hash: '7', path: null, before_san: 'Nc3', before_share: 100,
        before_win_pct: 60, before_total: 5, after_san: 'Nf3', after_share: 100, after_win_pct: 66.7, after_total: 6 }],
    })))
    render(<RepertoireChangesList color="w" minGames={3} onJumpToPath={vi.fn()} onOpenFlip={vi.fn()} />)

    await screen.findByText(/Nc3/)
    const jumpButton = screen.getByText('Jump here') as HTMLButtonElement
    expect(jumpButton.disabled).toBe(true)
    expect(screen.getByText(/no single verified move order/i)).toBeInTheDocument()
  })

  it('shows an empty state when there are no changes', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => [] })))
    render(<RepertoireChangesList color="w" minGames={3} onJumpToPath={vi.fn()} onOpenFlip={vi.fn()} />)
    expect(await screen.findByText(/no repertoire changes found/i)).toBeInTheDocument()
  })
})

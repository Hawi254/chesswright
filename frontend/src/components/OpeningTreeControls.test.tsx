import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OpeningTreeControls from './OpeningTreeControls'

describe('OpeningTreeControls', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls onColorChange when the color toggle is clicked', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => [] })))
    const onColorChange = vi.fn()
    render(<OpeningTreeControls color="w" onColorChange={onColorChange} minGames={3}
      onMinGamesChange={vi.fn()} onJumpToPath={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /black/i }))
    expect(onColorChange).toHaveBeenCalledWith('b')
  })

  it('calls onMinGamesChange when the slider moves', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => [] })))
    const onMinGamesChange = vi.fn()
    render(<OpeningTreeControls color="w" onColorChange={vi.fn()} minGames={3}
      onMinGamesChange={onMinGamesChange} onJumpToPath={vi.fn()} />)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '5' } })
    expect(onMinGamesChange).toHaveBeenCalledWith(5)
  })

  it('jumps to the resolved path when a family search result is selected', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/api/openings/table')) {
        // get_openings_table (dashboard/data/openings.py) surfaces the DB's
        // raw player_color values ('white'/'black'), not the 'w'/'b'
        // shorthand this component's own color prop uses -- confirmed
        // against the real query and test_api_openings.py's fixtures.
        return Promise.resolve({ ok: true, json: async () => [{ opening_family: 'Sicilian Defense', player_color: 'white' }] })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ path: ['e4', 'c5'] }) })
    })
    vi.stubGlobal('fetch', fetchMock)
    const onJumpToPath = vi.fn()
    render(<OpeningTreeControls color="w" onColorChange={vi.fn()} minGames={3}
      onMinGamesChange={vi.fn()} onJumpToPath={onJumpToPath} />)

    fireEvent.click(screen.getByText(/jump to an opening/i))
    fireEvent.change(await screen.findByPlaceholderText(/jump to an opening/i), { target: { value: 'Sicilian' } })
    fireEvent.click(await screen.findByText('Sicilian Defense'))

    await waitFor(() => expect(onJumpToPath).toHaveBeenCalledWith(['e4', 'c5']))
  })
})

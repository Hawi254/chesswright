import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AddToReviewButton from './AddToReviewButton'

const PROPS = { includeMotifs: true, includeMoments: false, includeHoles: false, topN: 20 }

describe('AddToReviewButton', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders nothing when Pro is inactive', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ active: false }) })))
    const { container } = render(<MemoryRouter><AddToReviewButton {...PROPS} /></MemoryRouter>)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('posts sources and shows the added count when Pro is active', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/pro-status')) return Promise.resolve({ ok: true, json: async () => ({ active: true }) })
      if (url.includes('/add-to-review')) return Promise.resolve({ ok: true, json: async () => ({ added: 5 }) })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }))
    render(<MemoryRouter><AddToReviewButton {...PROPS} /></MemoryRouter>)
    const button = await screen.findByRole('button', { name: /Add to Review deck/i })
    fireEvent.click(button)
    expect(await screen.findByText(/Added 5 positions/i)).toBeInTheDocument()
  })
})

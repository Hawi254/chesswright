import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { STATIC_CANDIDATES } from './lib/navCandidates'

vi.mock('./hooks/usePageCandidates', () => ({
  usePageCandidates: () => ({ candidates: STATIC_CANDIDATES, usingFallback: false }),
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
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  })

  it('renders the correct stub for a direct URL navigation', () => {
    renderAt('/patterns')
    expect(screen.getByRole('heading', { name: 'Patterns & Tendencies' })).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TrainingPage from './TrainingPage'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TrainingPage />
    </MemoryRouter>,
  )
}

describe('TrainingPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('defaults to the Review tab when no ?tab= param is present', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ active: false }) })))
    renderAt('/training')
    expect(screen.getByRole('tab', { name: /Review/ })).toHaveAttribute('data-active')
  })

  it('shows the Build Set tab when ?tab=build is present', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => ([]) })))
    renderAt('/training?tab=build')
    expect(screen.getByRole('tab', { name: 'Build Set' })).toHaveAttribute('data-active')
  })
})

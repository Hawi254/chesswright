import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import CommandPalette from './CommandPalette'
import type { PageCandidate } from '../lib/navCandidates'

const candidates: PageCandidate[] = [
  { category: 'page', title: 'Overview', url_path: 'overview' },
  { category: 'page', title: 'Patterns & Tendencies', url_path: 'patterns' },
  {
    category: 'setting',
    title: 'Local timezone offset',
    url_path: 'settings/analytics-display',
    anchor: 'utc-offset',
  },
]

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: vi.fn() }
})

function renderPalette(open: boolean, onOpenChange: (open: boolean) => void) {
  return render(
    <MemoryRouter>
      <input aria-label="distractor" />
      <CommandPalette open={open} onOpenChange={onOpenChange} candidates={candidates} />
    </MemoryRouter>,
  )
}

describe('CommandPalette', () => {
  it('opens on Cmd/Ctrl+K even while focus is inside an unrelated input', async () => {
    const onOpenChange = vi.fn()
    renderPalette(false, onOpenChange)

    const distractor = screen.getByLabelText('distractor')
    distractor.focus()
    expect(distractor).toHaveFocus()

    await userEvent.keyboard('{Meta>}k{/Meta}')

    expect(onOpenChange).toHaveBeenCalledWith(true)
  })

  it('filters candidates as the user types and navigates on selection', async () => {
    const navigate = vi.fn()
    vi.mocked(useNavigate).mockReturnValue(navigate)
    const onOpenChange = vi.fn()
    renderPalette(true, onOpenChange)

    await userEvent.type(screen.getByPlaceholderText(/search/i), 'Patterns')
    expect(screen.getByText('Patterns & Tendencies')).toBeInTheDocument()
    expect(screen.queryByText('Overview')).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('Patterns & Tendencies'))

    expect(navigate).toHaveBeenCalledWith('/patterns')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('navigates to the category route and sets the field hash when selecting a setting with an anchor', async () => {
    const navigate = vi.fn()
    vi.mocked(useNavigate).mockReturnValue(navigate)
    const onOpenChange = vi.fn()
    renderPalette(true, onOpenChange)

    await userEvent.type(screen.getByPlaceholderText(/search/i), 'Local timezone')
    await userEvent.click(screen.getByText('Local timezone offset'))

    expect(navigate).toHaveBeenCalledWith('/settings/analytics-display#utc-offset')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

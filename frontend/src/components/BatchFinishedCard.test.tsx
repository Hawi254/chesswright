import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import BatchFinishedCard from './BatchFinishedCard'

describe('BatchFinishedCard', () => {
  it('shows the finished run number', () => {
    render(<MemoryRouter><BatchFinishedCard runId={42} onDismiss={() => {}} /></MemoryRouter>)
    expect(screen.getByText('Batch #42 finished.')).toBeInTheDocument()
  })

  it('renders the "See what changed" affordance as a link to the batch-impact page, pre-filled with runB', () => {
    render(<MemoryRouter><BatchFinishedCard runId={42} onDismiss={() => {}} /></MemoryRouter>)
    const link = screen.getByText('See what changed →')
    expect(link.tagName).toBe('A')
    expect(link).toHaveAttribute('href', '/batch-impact?runB=42')
  })

  it('calls onDismiss when the dismiss control is clicked', () => {
    const onDismiss = vi.fn()
    render(<MemoryRouter><BatchFinishedCard runId={42} onDismiss={onDismiss} /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})

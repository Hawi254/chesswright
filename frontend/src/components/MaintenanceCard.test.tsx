import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import MaintenanceCard from './MaintenanceCard'

describe('MaintenanceCard', () => {
  it('renders the headline and button label', () => {
    render(<MaintenanceCard headline="5 games need annotation." buttonLabel="Run annotation pass now"
                             onAction={() => {}} pending={false} error={null} />)
    expect(screen.getByText('5 games need annotation.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run annotation pass now' })).toBeInTheDocument()
  })

  it('calls onAction when clicked', () => {
    const onAction = vi.fn()
    render(<MaintenanceCard headline="h" buttonLabel="Go" onAction={onAction} pending={false} error={null} />)
    fireEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('disables the button and shows a working label while pending', () => {
    render(<MaintenanceCard headline="h" buttonLabel="Go" onAction={() => {}} pending={true} error={null} />)
    const button = screen.getByRole('button', { name: 'Working…' })
    expect(button).toBeDisabled()
  })

  it('shows an error message when present', () => {
    render(<MaintenanceCard headline="h" buttonLabel="Go" onAction={() => {}} pending={false} error="It broke." />)
    expect(screen.getByText('It broke.')).toBeInTheDocument()
  })
})

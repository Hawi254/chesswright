import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import VariationPanel from './VariationPanel'

describe('VariationPanel', () => {
  it('renders nothing when inactive', () => {
    const { container } = render(
      <VariationPanel
        active={false}
        branchPly={null}
        sans={[]}
        step={0}
        onStepTo={vi.fn()}
        onExit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the branch-move header and "Branch point" at step 0', () => {
    render(
      <VariationPanel
        active
        branchPly={2}
        sans={[]}
        step={0}
        onStepTo={vi.fn()}
        onExit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(screen.getByText('Variation from move 1 — 0 of 0 moves')).toBeInTheDocument()
    expect(screen.getByText('Branch point')).toBeInTheDocument()
  })

  it('formats a White-to-move branch SAN line without a leading ellipsis', () => {
    render(
      <VariationPanel
        active
        branchPly={2}
        sans={['Nf3', 'Nc6', 'Bb5']}
        step={3}
        onStepTo={vi.fn()}
        onExit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(screen.getByText('Line: 2. Nf3 Nc6 3. Bb5')).toBeInTheDocument()
  })

  it('formats a Black-to-move branch SAN line with a leading ellipsis', () => {
    render(
      <VariationPanel
        active
        branchPly={1}
        sans={['Nc6', 'Bb5']}
        step={2}
        onStepTo={vi.fn()}
        onExit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(screen.getByText('Line: 1… Nc6 2. Bb5')).toBeInTheDocument()
  })

  it('disables Prev at step 0 and Next at the end of the line', () => {
    render(
      <VariationPanel
        active
        branchPly={2}
        sans={['Nf3']}
        step={1}
        onStepTo={vi.fn()}
        onExit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: '< Prev' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next >' })).toBeDisabled()
  })

  it('calls onStepTo, onExit, and onDiscard from their respective buttons', () => {
    const onStepTo = vi.fn()
    const onExit = vi.fn()
    const onDiscard = vi.fn()
    render(
      <VariationPanel
        active
        branchPly={2}
        sans={['Nf3', 'Nc6']}
        step={1}
        onStepTo={onStepTo}
        onExit={onExit}
        onDiscard={onDiscard}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '< Prev' }))
    expect(onStepTo).toHaveBeenCalledWith(0)
    fireEvent.click(screen.getByRole('button', { name: 'Next >' }))
    expect(onStepTo).toHaveBeenCalledWith(2)
    fireEvent.click(screen.getByRole('button', { name: 'Exit' }))
    expect(onExit).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Discard variation' }))
    expect(onDiscard).toHaveBeenCalled()
  })
})

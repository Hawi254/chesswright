import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EndpointPicker, { applyChartClick } from './EndpointPicker'
import type { BatchImpactRun } from '../hooks/useBatchImpact'

const RUNS: BatchImpactRun[] = [
  { id: 3, label: 'Run #3 — 2026-07-03 — 10 games', gamesAnalyzed: 10, endedAt: '2026-07-03' },
  { id: 2, label: 'Run #2 — 2026-07-02 — 8 games', gamesAnalyzed: 8, endedAt: '2026-07-02' },
  { id: 1, label: 'Run #1 — 2026-07-01 — 5 games', gamesAnalyzed: 5, endedAt: '2026-07-01' },
]

describe('EndpointPicker', () => {
  it('renders From/To selects with a Start option and the current selection', () => {
    render(<EndpointPicker runs={RUNS} range={{ runA: 1, runB: 2 }} onChange={vi.fn()} />)
    expect(screen.getByText('Start (no history)')).toBeInTheDocument()
    expect(screen.getByLabelText('From')).toHaveValue('1')
    expect(screen.getByLabelText('To')).toHaveValue('2')
  })

  it('shows runA as the Start sentinel when null', () => {
    render(<EndpointPicker runs={RUNS} range={{ runA: null, runB: 2 }} onChange={vi.fn()} />)
    expect(screen.getByLabelText('From')).toHaveValue('start')
  })

  it('calls onChange with null when Start is selected', () => {
    const onChange = vi.fn()
    render(<EndpointPicker runs={RUNS} range={{ runA: 1, runB: 2 }} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('From'), { target: { value: 'start' } })
    expect(onChange).toHaveBeenCalledWith(null, 2)
  })

  it('calls onChange with a numeric runB when To changes', () => {
    const onChange = vi.fn()
    render(<EndpointPicker runs={RUNS} range={{ runA: 1, runB: 2 }} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '3' } })
    expect(onChange).toHaveBeenCalledWith(1, 3)
  })

  it('shows the "pick two different batches" hint when runA equals runB', () => {
    render(<EndpointPicker runs={RUNS} range={{ runA: 2, runB: 2 }} onChange={vi.fn()} />)
    expect(screen.getByText('Pick two different batches to see a diff.')).toBeInTheDocument()
  })

  it('does not show the hint when runA differs from runB', () => {
    render(<EndpointPicker runs={RUNS} range={{ runA: 1, runB: 2 }} onChange={vi.fn()} />)
    expect(screen.queryByText('Pick two different batches to see a diff.')).not.toBeInTheDocument()
  })
})

describe('applyChartClick', () => {
  it('first click sets runA to the clicked run, keeps runB, and records pendingFirst', () => {
    const result = applyChartClick(null, 5, 9)
    expect(result).toEqual({ runA: 5, runB: 9, pendingFirst: 5 })
  })

  it('second click sets runB to the new click and clears pendingFirst', () => {
    const result = applyChartClick(5, 9, 9)
    expect(result).toEqual({ runA: 5, runB: 9, pendingFirst: null })
  })

  it('swaps when the second click is numerically earlier than the first', () => {
    const result = applyChartClick(9, 5, 9)
    expect(result).toEqual({ runA: 5, runB: 9, pendingFirst: null })
  })

  it('a third click behaves like a first click again (pendingFirst was cleared by the second)', () => {
    const second = applyChartClick(5, 9, 9)
    const third = applyChartClick(second.pendingFirst, 7, second.runB)
    expect(third).toEqual({ runA: 7, runB: 9, pendingFirst: 7 })
  })
})

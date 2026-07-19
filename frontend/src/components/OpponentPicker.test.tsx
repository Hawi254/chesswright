import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OpponentPicker from './OpponentPicker'

describe('OpponentPicker', () => {
  it('lists every opponent by default', () => {
    render(<OpponentPicker opponents={['Alice', 'Bob']} onSelect={vi.fn()} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('filters the list as the user types', () => {
    render(<OpponentPicker opponents={['Alice', 'Bob']} onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText(/find an opponent/i)
    fireEvent.change(input, { target: { value: 'ali' } })
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.queryByText('Bob')).not.toBeInTheDocument()
  })

  it('calls onSelect with the opponent name when an item is chosen', () => {
    const onSelect = vi.fn()
    render(<OpponentPicker opponents={['Alice']} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Alice'))
    expect(onSelect).toHaveBeenCalledWith('Alice')
  })

  it('shows the empty state when no opponent matches', () => {
    render(<OpponentPicker opponents={['Alice']} onSelect={vi.fn()} />)
    const input = screen.getByPlaceholderText(/find an opponent/i)
    fireEvent.change(input, { target: { value: 'zzz' } })
    expect(screen.getByText(/no opponents found/i)).toBeInTheDocument()
  })
})

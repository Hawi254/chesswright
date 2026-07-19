import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Slider from './Slider'

describe('Slider', () => {
  it('renders the label and current value', () => {
    render(<Slider label="Minimum games" min={1} max={50} value={5} onChange={vi.fn()} />)
    expect(screen.getByText('Minimum games')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('calls onChange with a number when dragged', () => {
    const onChange = vi.fn()
    render(<Slider label="Minimum games" min={1} max={50} value={5} onChange={onChange} />)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '12' } })
    expect(onChange).toHaveBeenCalledWith(12)
  })

  it('sets min/max/value attributes on the underlying input', () => {
    render(<Slider label="Top N" min={5} max={50} value={20} onChange={vi.fn()} />)
    const input = screen.getByRole('slider') as HTMLInputElement
    expect(input.min).toBe('5')
    expect(input.max).toBe('50')
    expect(input.value).toBe('20')
  })
})

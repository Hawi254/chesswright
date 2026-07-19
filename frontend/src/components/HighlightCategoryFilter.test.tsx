import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import HighlightCategoryFilter from './HighlightCategoryFilter'

const COUNTS = { brilliant: 3, puzzle_conversion: 2, best_move_streak: 5, blown_mate: 1, great_escape: 0 }

describe('HighlightCategoryFilter', () => {
  it('renders an All chip plus one chip per category, with count badges', () => {
    render(<HighlightCategoryFilter counts={COUNTS} activeCategory="all" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /all/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /brilliant/i })).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: /great escape/i })).toHaveTextContent('0')
  })

  it('calls onSelect with the clicked category', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<HighlightCategoryFilter counts={COUNTS} activeCategory="all" onSelect={onSelect} />)
    await user.click(screen.getByRole('button', { name: /blown mate/i }))
    expect(onSelect).toHaveBeenCalledWith('blown_mate')
  })

  it('calls onSelect with "all" when the All chip is clicked', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<HighlightCategoryFilter counts={COUNTS} activeCategory="brilliant" onSelect={onSelect} />)
    await user.click(screen.getByRole('button', { name: /^all/i }))
    expect(onSelect).toHaveBeenCalledWith('all')
  })

  it('marks the active chip distinctly from inactive ones', () => {
    render(<HighlightCategoryFilter counts={COUNTS} activeCategory="brilliant" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /brilliant/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /^all/i })).toHaveAttribute('aria-pressed', 'false')
  })
})

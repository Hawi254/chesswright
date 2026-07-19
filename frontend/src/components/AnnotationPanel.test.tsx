import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AnnotationPanel from './AnnotationPanel'

const BASE_PROPS = {
  annotation: null,
  loading: false,
  onSave: vi.fn(),
  saveError: null,
  onAskClaude: vi.fn(),
  aiLoading: false,
  aiError: null,
  claudeKeyAvailable: true,
}

describe('AnnotationPanel', () => {
  it('renders all 7 glyph options', () => {
    render(<AnnotationPanel {...BASE_PROPS} />)
    for (const g of ['(none)', '!', '!!', '?', '??', '!?', '?!']) {
      expect(screen.getByRole('button', { name: g })).toBeInTheDocument()
    }
  })

  it('is collapsed by default when there is no existing content', () => {
    const { container } = render(<AnnotationPanel {...BASE_PROPS} />)
    const details = container.querySelector('details')
    expect(details?.hasAttribute('open')).toBe(false)
  })

  it('is expanded by default when the annotation has existing content', () => {
    const { container } = render(
      <AnnotationPanel
        {...BASE_PROPS}
        annotation={{
          id: 'a1', move_index: 1, glyph: '!', comment: null,
          ai_comment: null, ai_model: null, generated_at: null,
          variation_id: 'v1', game_id: null,
        }}
      />,
    )
    const details = container.querySelector('details')
    expect(details?.hasAttribute('open')).toBe(true)
  })

  it('calls onSave with the selected glyph and typed comment', () => {
    const onSave = vi.fn()
    render(<AnnotationPanel {...BASE_PROPS} onSave={onSave} />)

    fireEvent.click(screen.getByRole('button', { name: '!!' }))
    fireEvent.change(screen.getByPlaceholderText(/your note/i), { target: { value: 'Nice shot' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(onSave).toHaveBeenCalledWith('!!', 'Nice shot')
  })

  it('shows saveError text below the textarea when set', () => {
    render(<AnnotationPanel {...BASE_PROPS} saveError="Failed to save annotation. Try again." />)
    expect(screen.getByText('Failed to save annotation. Try again.')).toBeInTheDocument()
  })

  it('shows "Ask Claude to comment" when there is no existing AI comment', () => {
    render(<AnnotationPanel {...BASE_PROPS} />)
    expect(screen.getByRole('button', { name: 'Ask Claude to comment' })).toBeInTheDocument()
  })

  it('shows "Regenerate Claude comment" when an AI comment already exists', () => {
    render(
      <AnnotationPanel
        {...BASE_PROPS}
        annotation={{
          id: 'a1', move_index: 1, glyph: null, comment: null,
          ai_comment: 'Existing comment', ai_model: 'claude-sonnet-4-6', generated_at: '2026-07-14',
          variation_id: 'v1', game_id: null,
        }}
      />,
    )
    expect(screen.getByRole('button', { name: 'Regenerate Claude comment' })).toBeInTheDocument()
    expect(screen.getByText(/Existing comment/)).toBeInTheDocument()
    expect(screen.getByText(/Generated 2026-07-14/)).toBeInTheDocument()
  })

  it('calls onAskClaude with the current comment text', () => {
    const onAskClaude = vi.fn()
    render(<AnnotationPanel {...BASE_PROPS} onAskClaude={onAskClaude} />)

    fireEvent.change(screen.getByPlaceholderText(/your note/i), { target: { value: 'my note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask Claude to comment' }))
    expect(onAskClaude).toHaveBeenCalledWith('my note')
  })

  it('hides the AI-assist button and shows a caption when claudeKeyAvailable is false', () => {
    render(<AnnotationPanel {...BASE_PROPS} claudeKeyAvailable={false} />)
    expect(screen.queryByRole('button', { name: 'Ask Claude to comment' })).not.toBeInTheDocument()
    expect(screen.getByText('Add API key in Settings to enable AI annotation.')).toBeInTheDocument()
  })

  it('disables the AI-assist button while aiLoading', () => {
    render(<AnnotationPanel {...BASE_PROPS} aiLoading />)
    expect(screen.getByRole('button', { name: 'Ask Claude to comment' })).toBeDisabled()
  })

  it('shows aiError text when set', () => {
    render(<AnnotationPanel {...BASE_PROPS} aiError="No Anthropic API key configured." />)
    expect(screen.getByText('No Anthropic API key configured.')).toBeInTheDocument()
  })

  it('seeds the form from the fetched annotation once loading settles, not from the pre-fetch render', () => {
    // Mirrors how the real hooks behave: mount with loading=false and no
    // annotation yet (the fetch hasn't started), then loading=true while
    // it's in flight, then loading=false with the real data. Found live:
    // seeding on the first `!loading` render (the pre-fetch one) instead
    // of the true->false transition always left the form empty.
    const { rerender } = render(<AnnotationPanel {...BASE_PROPS} annotation={null} loading={false} />)
    rerender(<AnnotationPanel {...BASE_PROPS} annotation={null} loading />)
    rerender(
      <AnnotationPanel
        {...BASE_PROPS}
        loading={false}
        annotation={{
          id: 'a1', move_index: 4, glyph: '!!', comment: 'Nice shot',
          ai_comment: null, ai_model: null, generated_at: null,
          variation_id: null, game_id: 'g1',
        }}
      />,
    )
    expect(screen.getByPlaceholderText(/your note/i)).toHaveValue('Nice shot')
    expect(screen.getByRole('button', { name: '!!' }).className).toContain('bg-[var(--cw-copper)]/20')
  })
})

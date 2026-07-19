import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import NarrativePanel from './NarrativePanel'

function mockFetchSuccess(body: unknown) {
  return vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => body }))
}

describe('NarrativePanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders the cached narrative as markdown and the generate button', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/settings/claude-key-status') {
        return Promise.resolve({ ok: true, json: async () => ({ available: true }) })
      }
      return Promise.resolve({ ok: true, json: async () => ({ narrative: '**Bold synthesis**', generated_at: '2026-07-14' }) })
    }))

    render(
      <NarrativePanel
        useNarrative={() => ({
          narrative: '**Bold synthesis**', generatedAt: '2026-07-14', loading: false, error: false,
          generating: false, generateError: null, generate: vi.fn(),
        })}
        description="Test description"
        generateLabel="Generate synthesis"
        regenerateLabel="Regenerate synthesis"
      />,
    )
    await waitFor(() => expect(screen.getByText('Bold synthesis')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Regenerate synthesis' })).toBeInTheDocument()
  })

  it('shows the generate label and the API-key-missing message when no cached narrative exists and no key is configured', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ available: false }))

    render(
      <NarrativePanel
        useNarrative={() => ({
          narrative: null, generatedAt: null, loading: false, error: false,
          generating: false, generateError: null, generate: vi.fn(),
        })}
        description="Test description"
        generateLabel="Generate synthesis"
        regenerateLabel="Regenerate synthesis"
      />,
    )
    await waitFor(() =>
      expect(screen.getByText('Add your own Anthropic API key on the Settings page to enable this.')).toBeInTheDocument())
    const button = screen.getByRole('button', { name: 'Generate synthesis' })
    expect(button).toBeDisabled()
  })

  it('shows the generate error message when generation failed', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ available: true }))

    render(
      <NarrativePanel
        useNarrative={() => ({
          narrative: null, generatedAt: null, loading: false, error: false,
          generating: false, generateError: 'Claude API call failed: timeout', generate: vi.fn(),
        })}
        description="Test description"
        generateLabel="Generate synthesis"
        regenerateLabel="Regenerate synthesis"
      />,
    )
    await waitFor(() => expect(screen.getByText('Claude API call failed: timeout')).toBeInTheDocument())
  })

  it('disables the button while a generate request is in flight, even with a key configured', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ available: true }))

    render(
      <NarrativePanel
        useNarrative={() => ({
          narrative: null, generatedAt: null, loading: false, error: false,
          generating: true, generateError: null, generate: vi.fn(),
        })}
        description="Test description"
        generateLabel="Generate synthesis"
        regenerateLabel="Regenerate synthesis"
      />,
    )
    await waitFor(() => expect(screen.getByRole('button', { name: 'Generate synthesis' })).toBeDisabled())
  })
})

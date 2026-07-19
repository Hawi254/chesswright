import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useInsightsSynthesis, useInsightsCoaching } from './useInsightsNarratives'

function mockFetchSuccess(body: unknown) {
  return vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useInsightsSynthesis', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the cached synthesis narrative on mount', async () => {
    const fetchMock = mockFetchSuccess({ narrative: 'Synthesis text', generated_at: '2026-07-14' })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useInsightsSynthesis())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.narrative).toBe('Synthesis text')
    expect(fetchMock.mock.calls[0][0]).toContain('/api/insights/synthesis')
  })

  it('generate() posts to the synthesis generate endpoint and updates narrative', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ narrative: null, generated_at: null }))
    const { result } = renderHook(() => useInsightsSynthesis())
    await waitFor(() => expect(result.current.loading).toBe(false))

    vi.stubGlobal('fetch', mockFetchSuccess({ narrative: 'Generated synthesis' }))
    result.current.generate()
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.narrative).toBe('Generated synthesis')
    expect(result.current.generateError).toBeNull()
  })

  it('generate() surfaces the detail message on a 503', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ narrative: null, generated_at: null }))
    const { result } = renderHook(() => useInsightsSynthesis())
    await waitFor(() => expect(result.current.loading).toBe(false))

    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false, status: 503, json: async () => ({ detail: 'No Anthropic API key configured.' }),
    })))
    result.current.generate()
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.generateError).toBe('No Anthropic API key configured.')
  })
})

describe('useInsightsCoaching', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches the cached coaching narrative on mount', async () => {
    const fetchMock = mockFetchSuccess({ narrative: 'Coaching text', generated_at: '2026-07-14' })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useInsightsCoaching())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.narrative).toBe('Coaching text')
    expect(fetchMock.mock.calls[0][0]).toContain('/api/insights/coaching')
  })

  it('generate() posts to the coaching generate endpoint and updates narrative', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ narrative: null, generated_at: null }))
    const { result } = renderHook(() => useInsightsCoaching())
    await waitFor(() => expect(result.current.loading).toBe(false))

    vi.stubGlobal('fetch', mockFetchSuccess({ narrative: 'Generated coaching' }))
    result.current.generate()
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.narrative).toBe('Generated coaching')
  })
})

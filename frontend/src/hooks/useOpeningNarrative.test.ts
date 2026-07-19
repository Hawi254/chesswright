import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOpeningNarrative } from './useOpeningNarrative'

function mockFetchSuccess(body: unknown) {
  return vi.fn((_url: string) => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useOpeningNarrative', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('does not fetch when family/color are null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningNarrative(null, null))
    expect(result.current.loading).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches the cached narrative when family/color are set, URL-encoding both', async () => {
    const fetchMock = mockFetchSuccess({ narrative: 'Text', generated_at: '2026-07-14' })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useOpeningNarrative("Queen's Gambit", 'white'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.narrative).toBe('Text')
    expect(fetchMock.mock.calls[0][0]).toContain(encodeURIComponent("Queen's Gambit"))
  })

  it('generate() posts and updates narrative on success', async () => {
    const getMock = mockFetchSuccess({ narrative: null, generated_at: null })
    vi.stubGlobal('fetch', getMock)
    const { result } = renderHook(() => useOpeningNarrative('Sicilian Defense', 'white'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    vi.stubGlobal('fetch', mockFetchSuccess({ narrative: 'Generated' }))
    result.current.generate()
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.narrative).toBe('Generated')
    expect(result.current.generateError).toBeNull()
  })

  it('generate() surfaces the detail message on a 503', async () => {
    const getMock = mockFetchSuccess({ narrative: null, generated_at: null })
    vi.stubGlobal('fetch', getMock)
    const { result } = renderHook(() => useOpeningNarrative('Sicilian Defense', 'white'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false, status: 503, json: async () => ({ detail: 'No Anthropic API key configured.' }),
    })))
    result.current.generate()
    await waitFor(() => expect(result.current.generating).toBe(false))
    expect(result.current.generateError).toBe('No Anthropic API key configured.')
  })
})

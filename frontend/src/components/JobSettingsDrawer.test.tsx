import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import JobSettingsDrawer from './JobSettingsDrawer'

const SETTINGS = {
  depth: 18, multipv: 3, threads: 4, hashMb: 256, maxGames: 100, maxDuration: '2h',
}

describe('JobSettingsDrawer', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads and displays current settings when opened', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => SETTINGS })))
    render(<JobSettingsDrawer open={true} onOpenChange={() => {}} readOnly={false} />)

    await waitFor(() => expect(screen.getByDisplayValue('18')).toBeInTheDocument())
    expect(screen.getByDisplayValue('3')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2h')).toBeInTheDocument()
  })

  it('disables every input and hides Save when readOnly', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => SETTINGS })))
    render(<JobSettingsDrawer open={true} onOpenChange={() => {}} readOnly={true} />)

    await waitFor(() => expect(screen.getByDisplayValue('18')).toBeInTheDocument())
    expect(screen.getByDisplayValue('18')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save settings' })).not.toBeInTheDocument()
    expect(screen.getByText(/read-only while a batch is running/)).toBeInTheDocument()
  })

  it('calls save() with edited values when Save is clicked', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SETTINGS })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)

    render(<JobSettingsDrawer open={true} onOpenChange={() => {}} readOnly={false} />)
    await waitFor(() => expect(screen.getByDisplayValue('18')).toBeInTheDocument())

    fireEvent.change(screen.getByDisplayValue('18'), { target: { value: '22' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/analysis-jobs/settings'),
      expect.objectContaining({ method: 'PUT' }),
    ))
  })

  it('shows a saveError message on a failed save', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => SETTINGS })
      .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: 'read-only' }) })
    vi.stubGlobal('fetch', fetchMock)

    render(<JobSettingsDrawer open={true} onOpenChange={() => {}} readOnly={false} />)
    await waitFor(() => expect(screen.getByDisplayValue('18')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(screen.getByText('read-only')).toBeInTheDocument())
  })

  it('threads/hash live under the Advanced disclosure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: async () => SETTINGS })))
    render(<JobSettingsDrawer open={true} onOpenChange={() => {}} readOnly={false} />)
    await waitFor(() => expect(screen.getByDisplayValue('18')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Advanced'))
    expect(screen.getByDisplayValue('4')).toBeInTheDocument()    // threads
    expect(screen.getByDisplayValue('256')).toBeInTheDocument()  // hashMb
  })
})

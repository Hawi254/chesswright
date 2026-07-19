import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IngestionSettingsPage from './IngestionSettingsPage'
import { useSettingsResource } from '../../hooks/useSettingsResource'

vi.mock('../../hooks/useSettingsResource')
const mockUseSettingsResource = vi.mocked(useSettingsResource)

const BASE = {
  value: { variantPolicy: 'skip', queueStrategy: 'interleaved_by_year' },
  loading: false,
  error: false,
  saving: false,
  saveError: null,
  save: vi.fn(),
  resetting: false,
  resetError: null,
  reset: vi.fn(),
}

describe('IngestionSettingsPage', () => {
  beforeEach(() => {
    mockUseSettingsResource.mockReturnValue(BASE)
  })

  it('shows a loading message while fetching', () => {
    mockUseSettingsResource.mockReturnValue({ ...BASE, value: null, loading: true })
    render(<IngestionSettingsPage />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders the current selections', () => {
    render(<IngestionSettingsPage />)
    expect(screen.getByLabelText('Non-standard variants')).toHaveValue('skip')
    expect(screen.getByLabelText('Analysis queue order')).toHaveValue('interleaved_by_year')
  })

  it('calls save() with the edited selections', async () => {
    const save = vi.fn()
    mockUseSettingsResource.mockReturnValue({ ...BASE, save })
    render(<IngestionSettingsPage />)
    await userEvent.selectOptions(screen.getByLabelText('Non-standard variants'), 'include')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(save).toHaveBeenCalledWith({ variantPolicy: 'include', queueStrategy: 'interleaved_by_year' })
  })

  it('calls reset() when Reset to defaults is clicked', async () => {
    const reset = vi.fn()
    mockUseSettingsResource.mockReturnValue({ ...BASE, reset })
    render(<IngestionSettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(reset).toHaveBeenCalled()
  })

  it('shows the inline save error when saveError is set', () => {
    mockUseSettingsResource.mockReturnValue({ ...BASE, saveError: 'bad value' })
    render(<IngestionSettingsPage />)
    expect(screen.getByText('bad value')).toBeInTheDocument()
  })
})

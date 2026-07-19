import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AnalyticsDisplaySettingsPage from './AnalyticsDisplaySettingsPage'
import { useSettingsResource } from '../../hooks/useSettingsResource'

vi.mock('../../hooks/useSettingsResource')
const mockUseSettingsResource = vi.mocked(useSettingsResource)

const BASE = {
  value: { utcOffsetHours: 0, minSampleSize: 20 },
  loading: false,
  error: false,
  saving: false,
  saveError: null,
  save: vi.fn(),
  resetting: false,
  resetError: null,
  reset: vi.fn(),
}

describe('AnalyticsDisplaySettingsPage', () => {
  beforeEach(() => {
    mockUseSettingsResource.mockReturnValue(BASE)
  })

  it('shows a loading message while fetching', () => {
    mockUseSettingsResource.mockReturnValue({ ...BASE, value: null, loading: true })
    render(<AnalyticsDisplaySettingsPage />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows an error message when the initial fetch fails', () => {
    mockUseSettingsResource.mockReturnValue({ ...BASE, value: null, loading: false, error: true })
    render(<AnalyticsDisplaySettingsPage />)
    expect(screen.getByText(/Couldn't load/)).toBeInTheDocument()
  })

  it('renders the current values in the form fields', () => {
    render(<AnalyticsDisplaySettingsPage />)
    expect(screen.getByLabelText('Local timezone offset (hours)')).toHaveValue(0)
    expect(screen.getByLabelText('Minimum sample size')).toHaveValue(20)
  })

  it('calls save() with the edited values on submit', async () => {
    const save = vi.fn()
    mockUseSettingsResource.mockReturnValue({ ...BASE, save })
    render(<AnalyticsDisplaySettingsPage />)
    await userEvent.clear(screen.getByLabelText('Minimum sample size'))
    await userEvent.type(screen.getByLabelText('Minimum sample size'), '15')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(save).toHaveBeenCalledWith({ utcOffsetHours: 0, minSampleSize: 15 })
  })

  it('shows the inline save error when saveError is set', () => {
    mockUseSettingsResource.mockReturnValue({ ...BASE, saveError: 'out of bounds' })
    render(<AnalyticsDisplaySettingsPage />)
    expect(screen.getByText('out of bounds')).toBeInTheDocument()
  })

  it('calls reset() when Reset to defaults is clicked', async () => {
    const reset = vi.fn()
    mockUseSettingsResource.mockReturnValue({ ...BASE, reset })
    render(<AnalyticsDisplaySettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(reset).toHaveBeenCalled()
  })
})

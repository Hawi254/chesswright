import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApiKeySettingsPage from './ApiKeySettingsPage'
import { useApiKeySettings } from '../../hooks/useApiKeySettings'

vi.mock('../../hooks/useApiKeySettings')
const mockUseApiKeySettings = vi.mocked(useApiKeySettings)

const BASE = {
  status: { configured: true, masked: 'sk-ant...7890', secureBackend: true },
  loading: false,
  error: false,
  saving: false,
  saveError: null,
  saveKey: vi.fn(),
  removing: false,
  removeError: null,
  removeKey: vi.fn(),
}

describe('ApiKeySettingsPage', () => {
  beforeEach(() => {
    mockUseApiKeySettings.mockReturnValue(BASE)
  })

  it('shows the masked key when configured', () => {
    render(<ApiKeySettingsPage />)
    expect(screen.getByText(/sk-ant\.\.\.7890/)).toBeInTheDocument()
  })

  it('shows a plaintext-storage warning when secureBackend is false', () => {
    mockUseApiKeySettings.mockReturnValue({
      ...BASE,
      status: { configured: true, masked: 'sk-ant...7890', secureBackend: false },
    })
    render(<ApiKeySettingsPage />)
    expect(screen.getByText(/less secure/i)).toBeInTheDocument()
  })

  it('calls saveKey() with the typed key on submit', async () => {
    const saveKey = vi.fn()
    mockUseApiKeySettings.mockReturnValue({ ...BASE, saveKey })
    render(<ApiKeySettingsPage />)
    await userEvent.type(screen.getByPlaceholderText('sk-ant-...'), 'sk-ant-abc123')
    await userEvent.click(screen.getByRole('button', { name: 'Save key' }))
    expect(saveKey).toHaveBeenCalledWith('sk-ant-abc123')
  })

  it('calls removeKey() when Remove saved key is clicked', async () => {
    const removeKey = vi.fn()
    mockUseApiKeySettings.mockReturnValue({ ...BASE, removeKey })
    render(<ApiKeySettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Remove saved key' }))
    expect(removeKey).toHaveBeenCalled()
  })

  it('shows the inline save error when saveError is set', () => {
    mockUseApiKeySettings.mockReturnValue({ ...BASE, saveError: 'API key is required.' })
    render(<ApiKeySettingsPage />)
    expect(screen.getByText('API key is required.')).toBeInTheDocument()
  })
})

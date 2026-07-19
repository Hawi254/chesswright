import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProSettingsPage from './ProSettingsPage'
import { useProLicense } from '../../hooks/useProLicense'

vi.mock('../../hooks/useProLicense')
const mockUseProLicense = vi.mocked(useProLicense)

const BASE = {
  active: false,
  license: { available: true, configured: false, masked: null, purchaseEmail: null },
  loading: false,
  error: false,
  activating: false,
  activateError: null,
  activateMessage: null,
  activate: vi.fn(),
  deactivating: false,
  deactivateError: null,
  deactivate: vi.fn(),
}

describe('ProSettingsPage', () => {
  beforeEach(() => {
    mockUseProLicense.mockReturnValue(BASE)
  })

  it('shows upsell copy when Pro is not available', () => {
    mockUseProLicense.mockReturnValue({ ...BASE, license: { available: false } })
    render(<ProSettingsPage />)
    expect(screen.getByText('Get Chesswright Pro')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Deactivate license' })).not.toBeInTheDocument()
  })

  it('shows an activation form when Pro is installed but not active', () => {
    render(<ProSettingsPage />)
    expect(screen.getByLabelText('License key')).toBeInTheDocument()
  })

  it('calls activate() with the typed key', async () => {
    const activate = vi.fn()
    mockUseProLicense.mockReturnValue({ ...BASE, activate })
    render(<ProSettingsPage />)
    await userEvent.type(screen.getByLabelText('License key'), 'valid-key')
    await userEvent.click(screen.getByRole('button', { name: 'Activate' }))
    expect(activate).toHaveBeenCalledWith('valid-key')
  })

  it('shows the masked key and Deactivate button when active', () => {
    mockUseProLicense.mockReturnValue({
      ...BASE,
      active: true,
      license: { available: true, configured: true, masked: 'cwpro-ab...1234', purchaseEmail: 'buyer@example.com' },
    })
    render(<ProSettingsPage />)
    expect(screen.getByText(/cwpro-ab\.\.\.1234/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deactivate license' })).toBeInTheDocument()
  })

  it('calls deactivate() when Deactivate license is clicked', async () => {
    const deactivate = vi.fn()
    mockUseProLicense.mockReturnValue({
      ...BASE,
      active: true,
      license: { available: true, configured: true, masked: 'cwpro-ab...1234', purchaseEmail: null },
      deactivate,
    })
    render(<ProSettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Deactivate license' }))
    expect(deactivate).toHaveBeenCalled()
  })
})

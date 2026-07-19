import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AccountDataSettingsPage from './AccountDataSettingsPage'
import { useDbImport } from '../../hooks/useDbImport'
import { useChesscomAccount } from '../../hooks/useChesscomAccount'

vi.mock('../../hooks/useDbImport')
vi.mock('../../hooks/useChesscomAccount')
const mockUseDbImport = vi.mocked(useDbImport)
const mockUseChesscomAccount = vi.mocked(useChesscomAccount)

const DB_IMPORT_BASE = {
  pending: null,
  importing: false,
  importError: null,
  startImport: vi.fn(),
  confirming: false,
  confirmError: null,
  confirmImport: vi.fn(),
  cancelImport: vi.fn(),
}

const CHESSCOM_BASE = {
  username: null,
  loading: false,
  error: false,
  pending: false,
  pendingError: null,
  connect: vi.fn(),
  disconnect: vi.fn(),
  syncNow: vi.fn(),
}

describe('AccountDataSettingsPage', () => {
  beforeEach(() => {
    mockUseDbImport.mockReturnValue(DB_IMPORT_BASE)
    mockUseChesscomAccount.mockReturnValue(CHESSCOM_BASE)
  })

  it('calls startImport() with the typed path', async () => {
    const startImport = vi.fn()
    mockUseDbImport.mockReturnValue({ ...DB_IMPORT_BASE, startImport })
    render(<AccountDataSettingsPage />)
    await userEvent.type(screen.getByLabelText('Path to the database file on this computer'), '/data/games.db')
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(startImport).toHaveBeenCalledWith('/data/games.db')
  })

  it('shows the confirm-username step once a pending import exists', () => {
    mockUseDbImport.mockReturnValue({
      ...DB_IMPORT_BASE,
      pending: { pendingId: 'abc', suggestedUsername: 'suggested_name' },
    })
    render(<AccountDataSettingsPage />)
    expect(screen.getByLabelText('Lichess username for this database')).toHaveValue('suggested_name')
  })

  it('calls confirmImport() with the (possibly edited) username', async () => {
    const confirmImport = vi.fn()
    mockUseDbImport.mockReturnValue({
      ...DB_IMPORT_BASE,
      pending: { pendingId: 'abc', suggestedUsername: 'suggested_name' },
      confirmImport,
    })
    render(<AccountDataSettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Use this database' }))
    expect(confirmImport).toHaveBeenCalledWith('suggested_name')
  })

  it('calls cancelImport() when Cancel is clicked', async () => {
    const cancelImport = vi.fn()
    mockUseDbImport.mockReturnValue({
      ...DB_IMPORT_BASE,
      pending: { pendingId: 'abc', suggestedUsername: 'x' },
      cancelImport,
    })
    render(<AccountDataSettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(cancelImport).toHaveBeenCalled()
  })

  it('shows a connect form when chess.com is not connected', () => {
    render(<AccountDataSettingsPage />)
    expect(screen.getByLabelText('Chess.com username')).toBeInTheDocument()
  })

  it('shows Sync now / Disconnect when chess.com is connected', () => {
    mockUseChesscomAccount.mockReturnValue({ ...CHESSCOM_BASE, username: 'my_chesscom' })
    render(<AccountDataSettingsPage />)
    expect(screen.getByText(/my_chesscom/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeInTheDocument()
  })
})

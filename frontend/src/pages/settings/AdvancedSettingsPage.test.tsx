import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdvancedSettingsPage from './AdvancedSettingsPage'
import { useSettingsResource } from '../../hooks/useSettingsResource'

vi.mock('../../hooks/useSettingsResource')
const mockUseSettingsResource = vi.mocked(useSettingsResource)

const SAMPLE = {
  pvMaxLen: 15,
  reuseEvals: true,
  consecutiveFailureLimit: 3,
  commitEveryNMoves: 1,
  berserkMaxClockFraction: 0.75,
  backlogQuota: 0.5,
  backlogQuotaWindow: 20,
  syncRequestTimeoutSeconds: 30,
  syncChesscomRequestTimeoutSeconds: 30,
}

const BASE = {
  value: SAMPLE,
  loading: false,
  error: false,
  saving: false,
  saveError: null,
  save: vi.fn(),
  resetting: false,
  resetError: null,
  reset: vi.fn(),
}

describe('AdvancedSettingsPage', () => {
  beforeEach(() => {
    mockUseSettingsResource.mockReturnValue(BASE)
  })

  it('is collapsed by default', () => {
    render(<AdvancedSettingsPage />)
    expect(screen.getByRole('group')).not.toHaveAttribute('open')
  })

  it('renders all 9 fields with their current values once expanded', async () => {
    render(<AdvancedSettingsPage />)
    await userEvent.click(screen.getByText('Advanced settings'))
    expect(screen.getByLabelText('Stored line length (plies)')).toHaveValue(15)
    expect(screen.getByLabelText(/Reuse a prior batch result/)).toBeChecked()
    expect(screen.getByLabelText('Stop after N consecutive game failures')).toHaveValue(3)
    expect(screen.getByLabelText('Commit every N moves')).toHaveValue(1)
    expect(screen.getByLabelText('Berserk clock fraction')).toHaveValue(0.75)
    expect(screen.getByLabelText('Backlog quota')).toHaveValue(0.5)
    expect(screen.getByLabelText('Backlog quota window (games)')).toHaveValue(20)
    expect(screen.getByLabelText('Lichess sync request timeout (s)')).toHaveValue(30)
    expect(screen.getByLabelText('Chess.com sync request timeout (s)')).toHaveValue(30)
  })

  it('saves all 9 fields together on one click', async () => {
    const save = vi.fn()
    mockUseSettingsResource.mockReturnValue({ ...BASE, save })
    render(<AdvancedSettingsPage />)
    await userEvent.click(screen.getByText('Advanced settings'))
    await userEvent.clear(screen.getByLabelText('Stored line length (plies)'))
    await userEvent.type(screen.getByLabelText('Stored line length (plies)'), '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save advanced settings' }))
    expect(save).toHaveBeenCalledWith({ ...SAMPLE, pvMaxLen: 30 })
  })

  it('shows the inline save error when saveError is set', async () => {
    mockUseSettingsResource.mockReturnValue({ ...BASE, saveError: 'out of bounds' })
    render(<AdvancedSettingsPage />)
    await userEvent.click(screen.getByText('Advanced settings'))
    expect(screen.getByText('out of bounds')).toBeInTheDocument()
  })
})

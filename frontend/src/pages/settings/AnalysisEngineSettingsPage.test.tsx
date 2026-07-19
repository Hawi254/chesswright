import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AnalysisEngineSettingsPage from './AnalysisEngineSettingsPage'
import { useEngineSettings } from '../../hooks/useEngineSettings'
import { useEngineProfiles } from '../../hooks/useEngineProfiles'

vi.mock('../../hooks/useEngineSettings')
vi.mock('../../hooks/useEngineProfiles')
const mockUseEngineSettings = vi.mocked(useEngineSettings)
const mockUseEngineProfiles = vi.mocked(useEngineProfiles)

const ENGINE_BASE = {
  engine: {
    path: '/usr/games/stockfish',
    detectedPath: '/usr/games/stockfish',
    live: { timeSec: 0.5, depth: 20, threads: 1, hashMb: 32, storeThreshold: 20, useLichessCloudEval: true },
  },
  loading: false,
  error: false,
  settingPath: false,
  pathError: null,
  setPath: vi.fn(),
  redetecting: false,
  redetectError: null,
  redetect: vi.fn(),
  savingLive: false,
  liveError: null,
  saveLive: vi.fn(),
  resetting: false,
  resetError: null,
  reset: vi.fn(),
  refetch: vi.fn(),
}

const PROFILES_BASE = {
  profiles: ['deep-analysis'],
  loading: false,
  error: false,
  saving: false,
  saveError: null,
  saveProfile: vi.fn(),
  applying: false,
  applyError: null,
  applyProfile: vi.fn(),
  deleting: false,
  deleteError: null,
  deleteProfile: vi.fn(),
}

describe('AnalysisEngineSettingsPage', () => {
  beforeEach(() => {
    mockUseEngineSettings.mockReturnValue(ENGINE_BASE)
    mockUseEngineProfiles.mockReturnValue(PROFILES_BASE)
  })

  it('shows a loading message while fetching', () => {
    mockUseEngineSettings.mockReturnValue({ ...ENGINE_BASE, engine: null, loading: true })
    render(<AnalysisEngineSettingsPage />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders the current engine path and live-engine field values', () => {
    render(<AnalysisEngineSettingsPage />)
    expect(screen.getByLabelText('Engine path')).toHaveValue('/usr/games/stockfish')
    expect(screen.getByLabelText('Depth limit')).toHaveValue(20)
  })

  it('calls redetect() when Re-detect is clicked', async () => {
    const redetect = vi.fn()
    mockUseEngineSettings.mockReturnValue({ ...ENGINE_BASE, redetect })
    render(<AnalysisEngineSettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Re-detect' }))
    expect(redetect).toHaveBeenCalled()
  })

  it('calls setPath() with the typed path when Set path is clicked', async () => {
    const setPath = vi.fn()
    mockUseEngineSettings.mockReturnValue({ ...ENGINE_BASE, setPath })
    render(<AnalysisEngineSettingsPage />)
    await userEvent.clear(screen.getByLabelText('Engine path'))
    await userEvent.type(screen.getByLabelText('Engine path'), '/opt/stockfish')
    await userEvent.click(screen.getByRole('button', { name: 'Set path' }))
    expect(setPath).toHaveBeenCalledWith('/opt/stockfish')
  })

  it('calls saveLive() with edited live-engine values', async () => {
    const saveLive = vi.fn()
    mockUseEngineSettings.mockReturnValue({ ...ENGINE_BASE, saveLive })
    render(<AnalysisEngineSettingsPage />)
    await userEvent.clear(screen.getByLabelText('Depth limit'))
    await userEvent.type(screen.getByLabelText('Depth limit'), '25')
    await userEvent.click(screen.getByRole('button', { name: 'Save and restart engine' }))
    expect(saveLive).toHaveBeenCalledWith(expect.objectContaining({ depth: 25 }))
  })

  it('renders saved profiles and calls applyProfile() + refetch() on Apply', async () => {
    const applyProfile = vi.fn().mockResolvedValue(undefined)
    const refetch = vi.fn()
    mockUseEngineProfiles.mockReturnValue({ ...PROFILES_BASE, applyProfile })
    mockUseEngineSettings.mockReturnValue({ ...ENGINE_BASE, refetch })
    render(<AnalysisEngineSettingsPage />)
    expect(screen.getByText('deep-analysis')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(applyProfile).toHaveBeenCalledWith('deep-analysis')
    expect(refetch).toHaveBeenCalled()
  })

  it('calls reset() when Reset to defaults is clicked', async () => {
    const reset = vi.fn()
    mockUseEngineSettings.mockReturnValue({ ...ENGINE_BASE, reset })
    render(<AnalysisEngineSettingsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(reset).toHaveBeenCalled()
  })
})

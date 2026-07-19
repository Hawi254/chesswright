import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import OpeningsPage from './OpeningsPage'

const mockOpeningsTableSection = vi.fn(() => <div data-testid="your-openings" />)
vi.mock('../components/OpeningsTableSection', () => ({ default: () => mockOpeningsTableSection() }))

const mockRepeatedPositionsSection = vi.fn(() => <div data-testid="repeated-positions" />)
vi.mock('../components/RepeatedPositionsSection', () => ({ default: () => mockRepeatedPositionsSection() }))

const mockRepertoireHolesSection = vi.fn(() => <div data-testid="repertoire-holes" />)
vi.mock('../components/RepertoireHolesSection', () => ({ default: () => mockRepertoireHolesSection() }))

const mockPlyAccuracySection = vi.fn(() => <div data-testid="ply-accuracy" />)
vi.mock('../components/PlyAccuracySection', () => ({ default: () => mockPlyAccuracySection() }))

describe('OpeningsPage', () => {
  it('mounts the "Your openings" tab first and does not mount the other three yet', () => {
    render(<OpeningsPage />)
    expect(screen.getByTestId('your-openings')).toBeInTheDocument()
    expect(screen.queryByTestId('repeated-positions')).not.toBeInTheDocument()
    expect(screen.queryByTestId('repertoire-holes')).not.toBeInTheDocument()
    expect(screen.queryByTestId('ply-accuracy')).not.toBeInTheDocument()
  })

  it('mounts a section only once its tab is first opened', async () => {
    const user = userEvent.setup()
    render(<OpeningsPage />)
    expect(mockRepeatedPositionsSection).not.toHaveBeenCalled()

    await user.click(screen.getByRole('tab', { name: /most-repeated positions/i }))
    await waitFor(() => expect(screen.getByTestId('repeated-positions')).toBeInTheDocument())
    expect(mockRepeatedPositionsSection).toHaveBeenCalledTimes(1)
  })

  it('switching away from a tab unmounts it', async () => {
    const user = userEvent.setup()
    render(<OpeningsPage />)
    await user.click(screen.getByRole('tab', { name: /repertoire holes/i }))
    await waitFor(() => expect(screen.getByTestId('repertoire-holes')).toBeInTheDocument())

    await user.click(screen.getByRole('tab', { name: /your openings/i }))
    await waitFor(() => expect(screen.queryByTestId('repertoire-holes')).not.toBeInTheDocument())
  })
})

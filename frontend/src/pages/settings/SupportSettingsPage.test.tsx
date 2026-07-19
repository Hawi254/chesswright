import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SupportSettingsPage from './SupportSettingsPage'

describe('SupportSettingsPage', () => {
  it('renders links to GitHub Sponsors and Open Collective', () => {
    render(<SupportSettingsPage />)
    expect(screen.getByRole('link', { name: /GitHub Sponsors/ })).toHaveAttribute(
      'href',
      'https://github.com/sponsors/Hawi254',
    )
    expect(screen.getByRole('link', { name: /Open Collective/ })).toHaveAttribute(
      'href',
      'https://opencollective.com/chesswright',
    )
  })
})

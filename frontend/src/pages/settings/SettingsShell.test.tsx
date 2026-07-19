import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import SettingsShell from './SettingsShell'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="settings" element={<SettingsShell />}>
          <Route path="account-data" element={<div>Account & Data content</div>} />
          <Route path="analysis-engine" element={<div>Analysis Engine content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('SettingsShell', () => {
  it('renders all 8 category links in the rail', () => {
    renderAt('/settings/account-data')
    expect(screen.getByRole('link', { name: 'Account & Data' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Analysis Engine' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Analytics & Display' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ingestion' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Advanced' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Anthropic API key' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chesswright Pro' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Support' })).toBeInTheDocument()
  })

  it('highlights the active category link', () => {
    renderAt('/settings/account-data')
    expect(screen.getByRole('link', { name: 'Account & Data' })).toHaveClass('border-[var(--cw-copper)]')
    expect(screen.getByRole('link', { name: 'Analysis Engine' })).toHaveClass('border-transparent')
  })

  it('renders the matched child route content in the detail pane', () => {
    renderAt('/settings/analysis-engine')
    expect(screen.getByText('Analysis Engine content')).toBeInTheDocument()
  })

  it('opens an ancestor <details> and highlights the target field when a hash is present', () => {
    render(
      <MemoryRouter initialEntries={['/settings/advanced#pv-max-len']}>
        <Routes>
          <Route path="settings" element={<SettingsShell />}>
            <Route
              path="advanced"
              element={
                <details>
                  <summary>Advanced settings</summary>
                  <label id="pv-max-len">Stored line length (plies)</label>
                </details>
              }
            />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const details = screen.getByText('Stored line length (plies)').closest('details')
    expect(details).toHaveAttribute('open')
  })
})

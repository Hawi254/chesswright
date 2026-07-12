import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PageStub from './PageStub'

describe('PageStub', () => {
  it('renders the given title and a not-yet-migrated notice', () => {
    render(<PageStub title="Patterns & Tendencies" />)
    expect(screen.getByText('Patterns & Tendencies')).toBeInTheDocument()
    expect(screen.getByText(/not yet migrated/i)).toBeInTheDocument()
  })
})

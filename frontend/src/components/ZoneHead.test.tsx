import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ZoneHead from './ZoneHead'

describe('ZoneHead', () => {
  it('renders the eyebrow and title', () => {
    render(<ZoneHead eyebrow="Who you are" title="Your chess identity" />)
    expect(screen.getByText('Who you are')).toBeInTheDocument()
    expect(screen.getByText('Your chess identity')).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import TrainingQueueTeaser from './TrainingQueueTeaser'
import type { Finding } from '../hooks/useOverviewData'

function renderTeaser(findings: Finding[]) {
  return render(
    <MemoryRouter>
      <TrainingQueueTeaser findings={findings} />
    </MemoryRouter>,
  )
}

describe('TrainingQueueTeaser', () => {
  it('shows the top weakness findings by severity, capped at 3', () => {
    const findings: Finding[] = [
      { title: 'Low weakness', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'tactical' },
      { title: 'High weakness', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'time' },
      { title: 'Medium weakness', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'medium', category: 'defense' },
      { title: 'A strength', headline: 'h', detail: 'd', polarity: 'strength', severity: 'high', category: 'tactical' },
    ]
    renderTeaser(findings)
    const items = screen.getAllByTestId('training-queue-item')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('High weakness')
    expect(items[1]).toHaveTextContent('Medium weakness')
    expect(items[2]).toHaveTextContent('Low weakness')
    expect(screen.queryByText('A strength')).not.toBeInTheDocument()
  })

  it('links to /training?tab=weaknesses', () => {
    renderTeaser([
      { title: 'A weakness', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'high', category: 'tactical' },
    ])
    expect(screen.getByRole('link', { name: /Open Training/i })).toHaveAttribute('href', '/training?tab=weaknesses')
  })

  it('renders nothing when there are no weakness findings', () => {
    const { container } = renderTeaser([
      { title: 'A strength', headline: 'h', detail: 'd', polarity: 'strength', severity: 'high', category: 'tactical' },
    ])
    expect(container).toBeEmptyDOMElement()
  })
})

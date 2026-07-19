import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RunTelemetry from './RunTelemetry'

describe('RunTelemetry', () => {
  it('renders nothing when telemetry is null', () => {
    const { container } = render(<RunTelemetry telemetry={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows "Off" for cache hit rate when reuse evals are disabled', () => {
    render(<RunTelemetry telemetry={{ reuseEvalsOn: false, cacheHitRate: null, estTimeSavedSec: null, eta: null }} />)
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  it('shows "N/A" for cache hit rate when nothing is eligible yet', () => {
    render(<RunTelemetry telemetry={{ reuseEvalsOn: true, cacheHitRate: null, estTimeSavedSec: null, eta: null }} />)
    expect(screen.getByText('N/A')).toBeInTheDocument()
  })

  it('shows a rounded percentage for a real cache hit rate', () => {
    render(<RunTelemetry telemetry={{ reuseEvalsOn: true, cacheHitRate: 0.503, estTimeSavedSec: 45, eta: 120 }} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows "calculating…" for ETA when eta is null', () => {
    render(<RunTelemetry telemetry={{ reuseEvalsOn: true, cacheHitRate: null, estTimeSavedSec: null, eta: null }} />)
    expect(screen.getByText('calculating…')).toBeInTheDocument()
  })

  it('formats a real ETA in seconds as h/m/s', () => {
    render(<RunTelemetry telemetry={{ reuseEvalsOn: true, cacheHitRate: 0.5, estTimeSavedSec: 90, eta: 3725 }} />)
    expect(screen.getByText('1h 2m')).toBeInTheDocument()
    expect(screen.getByText('1m 30s')).toBeInTheDocument()  // est. time saved: 90s
  })

  it('shows a placeholder when est. time saved is not yet available', () => {
    render(<RunTelemetry telemetry={{ reuseEvalsOn: true, cacheHitRate: null, estTimeSavedSec: null, eta: null }} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RangeRecords from './RangeRecords'
import type { BatchImpactRecord } from '../hooks/useBatchImpact'

describe('RangeRecords', () => {
  it('renders nothing when records is empty', () => {
    const { container } = render(<RangeRecords records={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one line per record', () => {
    const records: BatchImpactRecord[] = [
      { runId: 2, label: 'Run #2 — 2026-07-02 — 5 games', metric: 'acpl', value: 10, priorBest: 50 },
      { runId: 3, label: 'Run #3 — 2026-07-03 — 5 games', metric: 'blunder_rate', value: 2, priorBest: null },
    ]
    render(<RangeRecords records={records} />)
    expect(screen.getByText('Records set in this range')).toBeInTheDocument()
    expect(screen.getByText(/Run #2.*ACPL.*10\.0.*beating 50\.0/)).toBeInTheDocument()
    expect(screen.getByText(/Run #3.*blunder rate.*2\.0/)).toBeInTheDocument()
  })
})

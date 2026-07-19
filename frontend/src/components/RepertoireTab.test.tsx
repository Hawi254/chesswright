import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RepertoireTab from './RepertoireTab'

const ROWS = [
  { color: 'black' as const, opening: 'Sicilian Defense', n_games: 5, score_pct: 40.0, avg_cpl: 55.0, blunder_pct: 12.0 },
  { color: 'white' as const, opening: 'Italian Game', n_games: 9, score_pct: 60.0, avg_cpl: 30.0, blunder_pct: 3.0 },
]

describe('RepertoireTab', () => {
  it('defaults to sorting by games descending', () => {
    render(<RepertoireTab repertoire={ROWS} />)
    const rows = screen.getAllByRole('row').slice(1)  // drop the header row
    expect(rows[0]).toHaveTextContent('Italian Game')
    expect(rows[1]).toHaveTextContent('Sicilian Defense')
  })

  it('re-sorts client-side when a column header is clicked', () => {
    render(<RepertoireTab repertoire={ROWS} />)
    fireEvent.click(screen.getByText(/Blunder/i))
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Sicilian Defense')  // 12.0% blunder, descending default on first click of a new column
  })

  it('toggles sort direction on repeated header clicks', () => {
    render(<RepertoireTab repertoire={ROWS} />)
    const header = screen.getByText(/Blunder/i)
    fireEvent.click(header)
    fireEvent.click(header)
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Italian Game')  // 3.0% blunder, now ascending
  })

  it('renders an intensity bar for score and blunder columns', () => {
    render(<RepertoireTab repertoire={ROWS} />)
    expect(screen.getAllByTestId('intensity-bar')).toHaveLength(4)  // 2 rows x (score + blunder)
  })

  it('renders -- for a null avg_cpl/blunder_pct instead of NaN', () => {
    render(<RepertoireTab repertoire={[{ ...ROWS[0], avg_cpl: null, blunder_pct: null }]} />)
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
  })
})

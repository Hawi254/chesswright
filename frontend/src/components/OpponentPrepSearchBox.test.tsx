import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OpponentPrepSearchBox from './OpponentPrepSearchBox'

describe('OpponentPrepSearchBox', () => {
  it('offers to load a matching known opponent', () => {
    const onLoadKnown = vi.fn()
    render(
      <OpponentPrepSearchBox knownOpponents={['DrNykterstein']} onLoadKnown={onLoadKnown} onScoutNew={vi.fn()} />,
    )
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'DrNykterstein' } })
    fireEvent.click(screen.getByText(/DrNykterstein/i))
    expect(onLoadKnown).toHaveBeenCalledWith('DrNykterstein')
  })

  it('offers to scout an unrecognized username, with a games-to-fetch stepper', () => {
    const onScoutNew = vi.fn()
    render(
      <OpponentPrepSearchBox knownOpponents={['DrNykterstein']} onLoadKnown={vi.fn()} onScoutNew={onScoutNew} />,
    )
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'someone_new' } })
    expect(screen.getByText(/Scout someone_new/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/games to fetch/i)).toBeInTheDocument()

    fireEvent.click(screen.getByText(/Scout someone_new/i))
    expect(onScoutNew).toHaveBeenCalledWith('someone_new', 50)
  })

  it('does not show the games-to-fetch stepper when the search box is empty', () => {
    render(<OpponentPrepSearchBox knownOpponents={[]} onLoadKnown={vi.fn()} onScoutNew={vi.fn()} />)
    expect(screen.queryByLabelText(/games to fetch/i)).not.toBeInTheDocument()
  })
})

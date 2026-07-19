import { describe, expect, it } from 'vitest'
import { computeHeadline } from './pointsHeadline'

describe('computeHeadline', () => {
  it('returns null when there are no leaks', () => {
    expect(computeHeadline([], [], [])).toBeNull()
  })

  it('picks the bucket with the most leaked points, not the most games', () => {
    const headline = computeHeadline(
      [
        { bucket: 'failed_hold', n_games: 10, leaked: 5 },
        { bucket: 'failed_conversion', n_games: 1, leaked: 12 },
      ],
      [], [],
    )
    expect(headline?.bucket).toBe('failed_conversion')
    expect(headline?.totalLeaked).toBe(17)
  })

  it('adds a costliest-slice detail sentence only for failed_conversion, using the top phase/band by leaked points', () => {
    const headline = computeHeadline(
      [{ bucket: 'failed_conversion', n_games: 3, leaked: 10 }],
      [
        { adv_band: 'clearly better (70-80%)', n_games: 1, leaked: 2 },
        { adv_band: 'completely winning (90%+)', n_games: 2, leaked: 8 },
      ],
      [
        { conv_phase: 'opening', n_games: 1, leaked: 3 },
        { conv_phase: 'middlegame', n_games: 2, leaked: 7 },
      ],
    )
    expect(headline?.detail).toContain('middlegame')
    expect(headline?.detail).toContain('completely winning (90%+)')
  })

  it('has no detail sentence for missed_swindle or failed_hold', () => {
    const swindle = computeHeadline([{ bucket: 'missed_swindle', n_games: 2, leaked: 4 }], [], [])
    const hold = computeHeadline([{ bucket: 'failed_hold', n_games: 2, leaked: 4 }], [], [])
    expect(swindle?.detail).toBeNull()
    expect(hold?.detail).toBeNull()
  })
})

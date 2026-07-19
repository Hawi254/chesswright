import { describe, expect, it } from 'vitest'
import { activeChipsFor, BADGE_CHIPS, BADGE_LEGEND, TONE_CLASSES } from './badges'

const GAME_WITH_BADGES = {
  is_comeback: true, is_giant_killing: false, is_brilliant_find: true,
  is_blunder_fest: false, is_nail_biter: false,
}

const GAME_NO_BADGES = {
  is_comeback: false, is_giant_killing: false, is_brilliant_find: false,
  is_blunder_fest: false, is_nail_biter: false,
}

describe('badges', () => {
  it('lists all 5 badge chip definitions', () => {
    expect(BADGE_CHIPS.map((c) => c.key)).toEqual([
      'is_comeback', 'is_giant_killing', 'is_brilliant_find', 'is_blunder_fest', 'is_nail_biter',
    ])
  })

  it('has a tone class for each of the 3 tones', () => {
    expect(Object.keys(TONE_CLASSES)).toEqual(['positive', 'negative', 'neutral'])
  })

  it('returns only the active chips for a game', () => {
    const chips = activeChipsFor(GAME_WITH_BADGES)
    expect(chips.map((c) => c.label)).toEqual(['Comeback', 'Brilliant find'])
  })

  it('returns an empty array for a game with no badges', () => {
    expect(activeChipsFor(GAME_NO_BADGES)).toEqual([])
  })

  it('exposes the legend text', () => {
    expect(BADGE_LEGEND).toContain('Comeback: won/drew after being clearly lost.')
  })
})

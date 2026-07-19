import { describe, expect, it } from 'vitest'
import { relatedFindingFor } from './relatedFindings'

describe('relatedFindingFor', () => {
  it('returns the pair when both titles are present', () => {
    const present = new Set(['Clock pressure and blunder rate', 'Piece blunder hot-spot'])
    const pair = relatedFindingFor('Clock pressure and blunder rate', present)
    expect(pair).not.toBeNull()
    expect(pair?.titles).toContain('Piece blunder hot-spot')
  })

  it('is symmetric -- looking up from either side of the pair returns the same pair', () => {
    const present = new Set(['Clock pressure and blunder rate', 'Piece blunder hot-spot'])
    const fromA = relatedFindingFor('Clock pressure and blunder rate', present)
    const fromB = relatedFindingFor('Piece blunder hot-spot', present)
    expect(fromA).toEqual(fromB)
  })

  it('returns null when only one title of the pair is present', () => {
    const present = new Set(['Clock pressure and blunder rate'])
    expect(relatedFindingFor('Clock pressure and blunder rate', present)).toBeNull()
  })

  it('returns null for a title with no configured pair', () => {
    const present = new Set(['Some unrelated finding', 'Clock pressure and blunder rate', 'Piece blunder hot-spot'])
    expect(relatedFindingFor('Some unrelated finding', present)).toBeNull()
  })
})

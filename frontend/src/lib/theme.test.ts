import { describe, expect, it } from 'vitest'
import { THEME } from './theme'

describe('THEME', () => {
  it('matches the dashboard/theme.py palette exactly', () => {
    expect(THEME.bg).toBe('#14181F')
    expect(THEME.bgSecondary).toBe('#1E2530')
    expect(THEME.accentGold).toBe('#C19A4B')
    expect(THEME.positive).toBe('#6FA98C')
    expect(THEME.negative).toBe('#B0584F')
    expect(THEME.text).toBe('#E8E6E1')
  })
})

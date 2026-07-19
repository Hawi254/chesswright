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

  it('ports SEQUENTIAL_GOLD_COLORSCALE from dashboard/theme.py exactly', () => {
    expect(THEME.sequentialGold).toEqual([
      [0, '#1E2530'],
      [1, '#C19A4B'],
    ])
  })

  it('ports DIVERGING_COLORSCALE from dashboard/theme.py exactly', () => {
    expect(THEME.diverging).toEqual([
      [0, '#B0584F'],
      [0.5, '#1E2530'],
      [1, '#6FA98C'],
    ])
  })

  it('ports CATEGORICAL_SERIES/CATEGORICAL_OTHER from dashboard/theme.py exactly', () => {
    expect(THEME.categoricalSeries).toEqual(['#3987e5', '#c98500', '#9085e9', '#d95926'])
    expect(THEME.categoricalOther).toBe('#8A8F98')
  })
})

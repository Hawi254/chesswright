// Ported from dashboard/theme.py's palette (validated for WCAG AA contrast
// there via validate_palette.js) -- kept in sync by hand, same accepted
// duplication risk as navConfig.ts's group bucketing.
export const THEME = {
  bg: '#14181F',
  bgSecondary: '#1E2530',
  accentGold: '#C19A4B',
  positive: '#6FA98C',
  negative: '#B0584F',
  text: '#E8E6E1',
  textMuted: 'rgb(232 230 225 / 0.6)',
  cwCanvas: '#0B0F14',
  cwPanel2: '#0F141B',
  cwCopper: '#E08A3C',
  cwCyan: '#4FB8C4',
  cwMuted: 'rgb(236 238 240 / 0.6)',
  cwText: '#ECEEF0',
  // Ported 1:1 from dashboard/theme.py's SEQUENTIAL_GOLD_COLORSCALE
  // ([[0.0, BG_SECONDARY], [1.0, ACCENT_GOLD]]) -- same duplicate-by-hand
  // tradeoff as the rest of this palette.
  sequentialGold: [[0, '#1E2530'], [1, '#C19A4B']] as [number, string][],
  // Ported 1:1 from dashboard/theme.py's DIVERGING_COLORSCALE
  // ([[0.0, NEGATIVE], [0.5, BG_SECONDARY], [1.0, POSITIVE]]).
  diverging: [[0, '#B0584F'], [0.5, '#1E2530'], [1, '#6FA98C']] as [number, string][],
  // Ported 1:1 from dashboard/theme.py's CATEGORICAL_SERIES/CATEGORICAL_OTHER
  // -- same by-hand duplication tradeoff as the rest of this palette. Assign
  // in this fixed order by series rank; fold overflow series into
  // categoricalOther, never invent a 5th hue.
  categoricalSeries: ['#3987e5', '#c98500', '#9085e9', '#d95926'],
  categoricalOther: '#8A8F98',
} as const

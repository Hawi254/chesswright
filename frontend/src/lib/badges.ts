// Extracted from CareerHighlight.tsx (2026-07-13) so Game Explorer's
// filter pills/table badge column don't become a third hand-copy of the
// same chip logic and legend text -- same "small maintenance
// duplication, matches existing precedent" reasoning already accepted
// for the BADGE_LEGEND/chart-color constants elsewhere in this package,
// just consolidated one level.

export interface BadgeFlags {
  is_comeback: boolean
  is_giant_killing: boolean
  is_brilliant_find: boolean
  is_blunder_fest: boolean
  is_nail_biter: boolean
}

// Same legend text as dashboard/theme.py's BADGE_LEGEND -- kept in sync
// by hand, same precedent as the chart color constants in charts.ts/theme.ts.
export const BADGE_LEGEND =
  'Comeback: won/drew after being clearly lost. Giant-killing: beat a much ' +
  'higher-rated opponent. Brilliant find: a real sacrifice that worked. ' +
  'Blunder-fest: several big mistakes in one game. Nail-biter: result ' +
  'stayed in doubt until late.'

export type Tone = 'positive' | 'negative' | 'neutral'

export const TONE_CLASSES: Record<Tone, string> = {
  positive: 'bg-[var(--cw-copper)]/20 text-[var(--cw-copper)]',
  negative: 'bg-negative/20 text-negative',
  neutral: 'bg-[var(--cw-panel-2)] text-[var(--cw-muted)]',
}

export const BADGE_CHIPS: Array<{ key: keyof BadgeFlags; label: string; tone: Tone }> = [
  { key: 'is_comeback', label: 'Comeback', tone: 'positive' },
  { key: 'is_giant_killing', label: 'Giant-killing', tone: 'positive' },
  { key: 'is_brilliant_find', label: 'Brilliant find', tone: 'positive' },
  { key: 'is_blunder_fest', label: 'Blunder-fest', tone: 'negative' },
  { key: 'is_nail_biter', label: 'Nail-biter', tone: 'neutral' },
]

export function activeChipsFor<T extends BadgeFlags>(game: T) {
  return BADGE_CHIPS.filter((chip) => game[chip.key] === true)
}

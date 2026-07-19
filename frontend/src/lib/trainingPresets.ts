// Frontend port of dashboard/_common.py's DRILL_PRESETS -- keys must match
// Finding.title exactly (see Non-goals: no internal renaming, this is a
// duplicate lookup table by necessity, same accepted drift risk as
// navCandidates.ts/navConfig.ts's own hand-transcribed duplication).
export interface DrillPreset {
  includeMotifs: boolean
  includeMoments: boolean
  includeHoles: boolean
  motifFilter: string | null
}

export const DRILL_PRESETS: Record<string, DrillPreset> = {
  'Piece blunder hot-spot': {
    includeMotifs: true, includeMoments: false, includeHoles: false, motifFilter: null,
  },
  'Tactical highlights so far': {
    includeMotifs: true, includeMoments: false, includeHoles: false, motifFilter: null,
  },
  'King moves off the back rank': {
    includeMotifs: true, includeMoments: false, includeHoles: false, motifFilter: 'back_rank_mate',
  },
}

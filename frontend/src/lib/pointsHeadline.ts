import type { PointsAdvBandRow, PointsBucketSummary, PointsConvPhaseRow } from '../hooks/usePointsLedger'
import type { PointsBucketKey } from './pointsLabels'

export interface PointsHeadlineData {
  bucket: PointsBucketKey
  nGames: number
  leaked: number
  totalLeaked: number
  detail: string | null
}

export function computeHeadline(
  buckets: PointsBucketSummary[],
  advBand: PointsAdvBandRow[],
  convPhase: PointsConvPhaseRow[],
): PointsHeadlineData | null {
  if (buckets.length === 0) return null
  const top = [...buckets].sort((a, b) => b.leaked - a.leaked)[0]
  const totalLeaked = buckets.reduce((sum, b) => sum + b.leaked, 0)

  let detail: string | null = null
  if (top.bucket === 'failed_conversion' && advBand.length > 0 && convPhase.length > 0) {
    const topPhase = [...convPhase].sort((a, b) => b.leaked - a.leaked)[0]
    const topBand = [...advBand].sort((a, b) => b.leaked - a.leaked)[0]
    detail = `The costliest slice: positions that first became winning in the ${topPhase.conv_phase} ` +
      `(${topPhase.leaked.toFixed(0)} pts), most often at ${topBand.adv_band}.`
  }

  return { bucket: top.bucket, nGames: top.n_games, leaked: top.leaked, totalLeaked, detail }
}

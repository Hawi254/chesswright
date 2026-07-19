import { THEME } from './theme'

export type PointsBucketKey = 'failed_conversion' | 'missed_swindle' | 'failed_hold'

export const POINTS_BUCKET_LABEL: Record<PointsBucketKey, string> = {
  failed_conversion: 'Failed conversion',
  missed_swindle: 'Missed swindle',
  failed_hold: 'Failed hold',
}

// Fixed per-bucket hue, keyed on bucket identity rather than array
// position -- the API's `buckets` array is sorted by leaked points
// descending (summarize_buckets), so array index isn't stable identity.
export const POINTS_BUCKET_COLOR: Record<PointsBucketKey, string> = {
  failed_conversion: THEME.categoricalSeries[0],
  missed_swindle: THEME.categoricalSeries[1],
  failed_hold: THEME.categoricalSeries[2],
}

export const POINTS_REASON_LABEL: Record<string, string> = {
  hung_piece: 'Hung a piece',
  blown_mate: 'Blew a forced mate',
  time_pressure: 'Time pressure',
  other: 'Other / gradual give-back',
}

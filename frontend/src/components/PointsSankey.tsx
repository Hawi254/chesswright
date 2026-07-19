import Plot from 'react-plotly.js'
import { sankeyChart } from '../lib/charts'
import type { PointsBucketKey } from '../lib/pointsLabels'
import type { PointsBucketSummary } from '../hooks/usePointsLedger'

export default function PointsSankey({
  buckets,
  actualPoints,
  leakedPoints,
  onBucketClick,
}: {
  buckets: PointsBucketSummary[]
  actualPoints: number
  leakedPoints: number
  onBucketClick: (bucket: PointsBucketKey) => void
}) {
  const chart = sankeyChart(buckets, actualPoints, leakedPoints)

  function handleClick(event: { points: Array<{ customdata?: PointsBucketKey | null }> }) {
    const point = event.points?.[0]
    if (point?.customdata) onBucketClick(point.customdata)
  }

  return (
    <Plot
      {...chart}
      config={{ displayModeBar: false }}
      style={{ width: '100%' }}
      onClick={handleClick}
    />
  )
}

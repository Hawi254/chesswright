import Plot from 'react-plotly.js'
import { lineChart } from '../lib/charts'
import { THEME } from '../lib/theme'
import type { BatchImpactTrendRow } from '../hooks/useBatchImpact'

export interface BatchTrendChartProps {
  rows: BatchImpactTrendRow[]
  yKey: 'cumulativeAcpl' | 'cumulativeBlunderRate'
  yTitle: string
  color: string
  range: { runA: number | null; runB: number | null }
  onPointClick: (runId: number) => void
}

export default function BatchTrendChart({ rows, yKey, yTitle, color, range, onPointClick }: BatchTrendChartProps) {
  const plotted = rows.filter((r) => r[yKey] !== null)
  if (plotted.length < 2) {
    return <p className="text-xs text-[var(--cw-muted)]">Not enough annotated batches yet for a trend line.</p>
  }

  const chart = lineChart(plotted, 'runId', yKey, color, { yTitle })
  // Highlight the two selected endpoints so "the selected range is
  // visually marked between the two chosen points" (design spec, section
  // 3) without needing a separate shaded-region overlay.
  const isEndpoint = (runId: number) => runId === range.runA || runId === range.runB
  chart.data[0] = {
    ...chart.data[0],
    customdata: plotted.map((r) => r.runId),
    marker: {
      size: plotted.map((r) => (isEndpoint(r.runId) ? 10 : 5)),
      color: plotted.map((r) => (isEndpoint(r.runId) ? THEME.accentGold : color)),
    },
  }

  function handleClick(event: { points: Array<{ customdata?: number }> }) {
    const point = event.points?.[0]
    if (point?.customdata !== undefined) onPointClick(point.customdata)
  }

  return <Plot {...chart} config={{ displayModeBar: false }} style={{ width: '100%' }} onClick={handleClick} />
}

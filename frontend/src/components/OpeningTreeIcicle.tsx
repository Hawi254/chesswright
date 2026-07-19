import Plot from 'react-plotly.js'
import { openingTreeIcicleChart } from '../lib/charts'
import type { OpeningTreeMap } from '../lib/openingTreeMap'

export default function OpeningTreeIcicle({
  map, onNodeClick,
}: {
  map: OpeningTreeMap
  onNodeClick: (path: string[]) => void
}) {
  const chart = openingTreeIcicleChart(map)

  function handleClick(event: { points: Array<{ id: string }> }) {
    const point = event.points?.[0]
    if (!point?.id) return
    onNodeClick(point.id === 'root' ? [] : point.id.split('/'))
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

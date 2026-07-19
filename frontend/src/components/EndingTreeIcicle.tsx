import Plot from 'react-plotly.js'
import { icicleChart } from '../lib/charts'
import type { EndingTree } from '../lib/endingTree'

export default function EndingTreeIcicle({
  tree,
  onNodeClick,
}: {
  tree: EndingTree
  onNodeClick: (path: string) => void
}) {
  const chart = icicleChart(tree)

  function handleClick(event: { points: Array<{ id: string }> }) {
    const point = event.points?.[0]
    if (point?.id) onNodeClick(point.id)
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

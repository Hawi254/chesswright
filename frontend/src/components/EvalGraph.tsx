import Plot from 'react-plotly.js'
import type { WinProbPoint } from '../hooks/useGameDetail'
import { lineChart } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function EvalGraph({
  winProb,
  currentPly,
  onSelectPly,
}: {
  winProb: WinProbPoint[]
  currentPly: number | null
  onSelectPly: (ply: number) => void
}) {
  if (winProb.length < 2) {
    return (
      <p className="text-xs text-[var(--cw-muted)]">
        Not enough annotated moves yet to draw an evaluation graph for this game. It&apos;s
        likely been analyzed but not yet annotated -- check the Analysis Jobs page for games
        awaiting annotation.
      </p>
    )
  }

  const chart = lineChart(winProb, 'ply', 'player_win_prob', THEME.cwCopper, {
    height: 220,
    xTitle: "Turn (one player's move)",
    yTitle: 'Your win probability',
    paperBgcolor: THEME.cwCanvas,
    plotBgcolor: THEME.cwPanel2,
    axisColor: THEME.cwText,
    fill: true,
    referenceLine: { y: 0.5, color: THEME.cwCyan },
  })
  chart.layout.yaxis = { ...chart.layout.yaxis, range: [0, 1], tickformat: '.0%' }

  // A second, marker-only trace at the current ply -- keeps the graph in
  // sync with the board/move-list selection the same way MoveList
  // highlights the current move (see Task 14's live-verification
  // checklist: clicking a move must move this marker too, not just the
  // board). Plotly only auto-shows a legend once 2+ traces exist, so the
  // main line (invisible-by-default at 1 trace) needs showlegend: false
  // made explicit here too -- found live, a stray "trace 0" legend
  // appeared the moment this second trace was added.
  const currentPoint = winProb.find((p) => p.ply === currentPly)
  const data = currentPoint
    ? [
        { ...chart.data[0], showlegend: false },
        {
          x: [currentPoint.ply],
          y: [currentPoint.player_win_prob],
          type: 'scatter' as const,
          mode: 'markers' as const,
          marker: { size: 10, color: THEME.cwCyan },
          hoverinfo: 'skip' as const,
          showlegend: false,
        },
      ]
    : chart.data

  function handleClick(event: { points: Array<{ pointIndex: number }> }) {
    const point = event.points?.[0]
    if (!point) return
    const ply = winProb[point.pointIndex]?.ply
    if (ply !== undefined) onSelectPly(ply)
  }

  return (
    <div>
      <h2 className="font-condensed text-[11px] text-[var(--cw-text)]">Your win probability</h2>
      <Plot
        data={data}
        layout={chart.layout}
        config={{ displayModeBar: false }}
        style={{ width: '100%' }}
        onClick={handleClick}
      />
    </div>
  )
}

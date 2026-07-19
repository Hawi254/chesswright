import Plot from 'react-plotly.js'
import { dumbbellChart } from '../lib/charts'
import type { DumbbellRow } from '../lib/charts'

export interface DumbbellSectionProps {
  title: string
  caption?: string
  rows: DumbbellRow[]
  xTitle: string
  valueSuffix?: string
  minRows?: number
}

export default function DumbbellSection({ title, caption, rows, xTitle, valueSuffix = '', minRows = 1 }: DumbbellSectionProps) {
  if (rows.length < minRows) {
    return (
      <div className="mt-4">
        <h3 className="font-condensed text-sm font-bold text-[var(--cw-text)]">{title}</h3>
        <p className="mt-1 text-xs text-[var(--cw-muted)]">Not enough data yet in this range.</p>
      </div>
    )
  }
  const chart = dumbbellChart(rows, { xTitle, valueSuffix })
  return (
    <div className="mt-4">
      <h3 className="font-condensed text-sm font-bold text-[var(--cw-text)]">{title}</h3>
      {caption && <p className="mt-1 text-xs text-[var(--cw-muted)]">{caption}</p>}
      <Plot {...chart} config={{ displayModeBar: false }} style={{ width: '100%' }} />
    </div>
  )
}

import type { Layout, PlotData } from 'plotly.js'
import { THEME } from './theme'
import { END_TYPE_LABELS, RESIGNATION_REASON_LABELS } from './endingTreeLabels'
import type { EndingTree } from './endingTree'
import { POINTS_BUCKET_COLOR, POINTS_BUCKET_LABEL } from './pointsLabels'
import type { PointsBucketKey } from './pointsLabels'
import type { OpeningTreeMap } from './openingTreeMap'

// Matches --font-condensed (index.css) so axis text reads as part of the
// same instrument-panel system instead of Plotly's default Arial/sans.
const CHART_FONT_FAMILY = '"Archivo Narrow", "Arial Narrow", sans-serif'

function titleCase(column: string): string {
  return column
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function rgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

export interface LineChartOptions<T> {
  height?: number
  xTitle?: string
  yTitle?: string
  hoverExtra?: { column: keyof T & string; label: string }
  paperBgcolor?: string
  plotBgcolor?: string
  axisColor?: string
  fill?: boolean
  referenceLine?: { y: number; color: string }
}

// Generic (not Record<string, ...>) deliberately: plain interfaces like
// RatingPoint/AcplPoint have no index signature, so TS's direct
// assignability check against Record<string, X> rejects them at call
// sites -- keyof T sidesteps that entirely and also gets column-name
// typos caught at compile time.
export function lineChart<T>(
  rows: T[],
  x: keyof T & string,
  y: keyof T & string,
  color: string,
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? titleCase(y)

  let hovertemplate = `%{x}<br>${yTitle}: %{y:.2f}`
  let customdata: Array<string | number> | undefined
  if (options.hoverExtra) {
    const { column, label } = options.hoverExtra
    customdata = rows.map((row) => row[column] as unknown as string | number)
    hovertemplate += `<br>${label}: %{customdata}`
  }

  const trace = {
    x: rows.map((row) => row[x] as unknown as number),
    y: rows.map((row) => row[y] as unknown as number),
    type: 'scatter',
    mode: 'lines+markers',
    line: { color, width: 2 },
    marker: { size: 5 },
    customdata,
    hovertemplate: hovertemplate + '<extra></extra>',
    ...(options.fill ? { fill: 'tozeroy', fillcolor: rgba(color, 0.08) } : {}),
  } as Partial<PlotData>

  const axisColor = options.axisColor ?? THEME.text
  const axisTheme = {
    gridcolor: rgba(axisColor, 0.1),
    linecolor: rgba(axisColor, 0.33),
    tickfont: { color: axisColor },
    automargin: true,
  }

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...axisTheme },
    yaxis: { title: { text: yTitle }, ...axisTheme },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
    ...(options.referenceLine
      ? {
          shapes: [
            {
              type: 'line' as const, x0: 0, x1: 1, xref: 'paper' as const,
              y0: options.referenceLine.y, y1: options.referenceLine.y,
              line: { color: options.referenceLine.color, dash: 'dot' as const, width: 1 },
            },
          ],
        }
      : {}),
  }

  return { data: [trace], layout }
}

export function barChart<T>(
  rows: T[],
  x: keyof T & string,
  y: keyof T & string,
  color: string,
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? titleCase(y)
  const axisColor = options.axisColor ?? THEME.text

  const trace = {
    x: rows.map((row) => row[x] as unknown as number),
    y: rows.map((row) => row[y] as unknown as number),
    type: 'bar',
    marker: { color },
    hovertemplate: `%{x}<br>${yTitle}: %{y}<extra></extra>`,
  } as Partial<PlotData>

  const axisTheme = {
    gridcolor: rgba(axisColor, 0.1),
    linecolor: rgba(axisColor, 0.33),
    tickfont: { color: axisColor },
    automargin: true,
  }

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...axisTheme },
    yaxis: { title: { text: yTitle }, ...axisTheme },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
  }

  return { data: [trace], layout }
}

export interface OverlaySeries<T> {
  rows: T[]
  x: keyof T & string
  y: keyof T & string
  label: string
  color: string
}

function sharedAxisTheme(axisColor: string) {
  return {
    gridcolor: rgba(axisColor, 0.1),
    linecolor: rgba(axisColor, 0.33),
    tickfont: { color: axisColor },
    automargin: true,
  }
}

export function overlayBarChart<T>(
  seriesA: OverlaySeries<T>,
  seriesB: OverlaySeries<T>,
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(seriesA.x)
  const yTitle = options.yTitle ?? titleCase(seriesA.y)
  const axisColor = options.axisColor ?? THEME.text

  const data = [seriesA, seriesB].map(
    (s): Partial<PlotData> => ({
      x: s.rows.map((row) => row[s.x] as unknown as number),
      y: s.rows.map((row) => row[s.y] as unknown as number),
      type: 'bar',
      name: s.label,
      marker: { color: s.color },
      hovertemplate: `%{x}<br>${s.label}: %{y:.1f}<extra></extra>`,
    }),
  )

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    barmode: 'group',
    showlegend: true,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...sharedAxisTheme(axisColor) },
    yaxis: { title: { text: yTitle }, ...sharedAxisTheme(axisColor) },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
  }

  return { data, layout }
}

export interface GroupedBarChartOptions<T> extends LineChartOptions<T> {
  colors?: Record<string, string>
}

export function groupedBarChart<T>(
  rows: T[],
  x: keyof T & string,
  groupCol: keyof T & string,
  y: keyof T & string,
  options: GroupedBarChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? titleCase(y)
  const axisColor = options.axisColor ?? THEME.text

  const defaultColors = [THEME.accentGold, THEME.positive, THEME.negative]
  const groups = [...new Set(rows.map((row) => String(row[groupCol])))]

  const data: Partial<PlotData>[] = groups.map((group, i) => {
    const sub = rows.filter((row) => String(row[groupCol]) === group)
    const color = options.colors?.[group] ?? defaultColors[i % defaultColors.length]
    return {
      x: sub.map((row) => row[x] as unknown as string | number),
      y: sub.map((row) => row[y] as unknown as number),
      type: 'bar',
      name: group,
      marker: { color },
      hovertemplate: `%{x}<br>${group}<br>${yTitle}: %{y:.2f}<extra></extra>`,
    }
  })

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    barmode: 'group',
    showlegend: true,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...sharedAxisTheme(axisColor) },
    yaxis: { title: { text: yTitle }, ...sharedAxisTheme(axisColor) },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
  }

  return { data, layout }
}

export function stackedBarChart<T>(
  rows: T[],
  x: keyof T & string,
  groupCol: keyof T & string,
  y: keyof T & string,
  colors: Record<string, string>,
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? titleCase(y)
  const axisColor = options.axisColor ?? THEME.text

  const groups = [...new Set(rows.map((row) => String(row[groupCol])))]

  const data: Partial<PlotData>[] = groups.map((group) => {
    const sub = rows.filter((row) => String(row[groupCol]) === group)
    const color = colors[group]
    if (!color) {
      throw new Error(`stackedBarChart: no color provided for group "${group}"`)
    }
    return {
      x: sub.map((row) => row[x] as unknown as string | number),
      y: sub.map((row) => row[y] as unknown as number),
      type: 'bar',
      name: group,
      marker: { color, line: { color: THEME.bg, width: 2 } },
      hovertemplate: `%{x}<br>${group}: %{y:.1f}<extra></extra>`,
    }
  })

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    barmode: 'stack',
    showlegend: true,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...sharedAxisTheme(axisColor) },
    yaxis: { title: { text: yTitle }, ...sharedAxisTheme(axisColor) },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
  }

  return { data, layout }
}

export interface HeatmapOptions<T> {
  height?: number
  xTitle?: string
  yTitle?: string
  colorbarTitle?: string
  valueSuffix?: string
  hoverExtra?: { column: keyof T & string; label: string }
  paperBgcolor?: string
  plotBgcolor?: string
  axisColor?: string
  // Explicit axis category order, for axes that aren't safely derivable
  // by sorting the observed values -- e.g. Game Context's hour-of-day (0-
  // 23 numeric, but the default x-sort is lexicographic: "10" would sort
  // before "2") and day-of-week ("Mon".."Sun" labels, not numeric at all
  // -- the default y-sort/Number()-cast would produce NaN). When given,
  // the array is used verbatim as that axis's full category list (not
  // filtered to only observed values -- missing cells still render as
  // null/transparent, same as any other gap), and for y specifically, the
  // trace's own y values stay as the given strings instead of being cast
  // through Number(). Omit for axes the existing numeric-descending-y /
  // lexicographic-x default already handles correctly (e.g. the square-
  // blunder heatmap's file/rank axes).
  xOrder?: string[]
  yOrder?: string[]
}

// Takes long-form {x, y, z} triples (the API pivots server-side into a
// pandas DataFrame, then serializes it as long-form rows -- simpler to
// type/serialize than shipping a 2D matrix over JSON, see the design
// spec's decision 3) and re-pivots them into the 2D z-grid Plotly's
// `heatmap` trace type requires. Missing (x, y) combinations become
// `null` z-cells, which Plotly renders as empty/transparent.
export function heatmap<T>(
  cells: T[],
  x: keyof T & string,
  y: keyof T & string,
  z: keyof T & string,
  colorscale: Array<[number, string]>,
  options: HeatmapOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 380
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? titleCase(y)
  const axisColor = options.axisColor ?? THEME.text
  const valueSuffix = options.valueSuffix ?? ''

  const xValues = options.xOrder ?? [...new Set(cells.map((c) => String(c[x])))].sort()
  const yValues = options.yOrder ?? [...new Set(cells.map((c) => String(c[y])))].sort((a, b) => Number(b) - Number(a))

  const zGrid: Array<Array<number | null>> = yValues.map(() => xValues.map(() => null))
  const customGrid: Array<Array<string | number | null>> = yValues.map(() => xValues.map(() => null))

  for (const cell of cells) {
    const xi = xValues.indexOf(String(cell[x]))
    const yi = yValues.indexOf(String(cell[y]))
    zGrid[yi][xi] = cell[z] as unknown as number
    if (options.hoverExtra) {
      customGrid[yi][xi] = cell[options.hoverExtra.column] as unknown as string | number
    }
  }

  let hovertemplate = `%{y} / %{x}: %{z:.1f}${valueSuffix}`
  if (options.hoverExtra) {
    hovertemplate += `<br>${options.hoverExtra.label}: %{customdata}`
  }

  const trace = {
    x: xValues,
    y: options.yOrder ? yValues : yValues.map((v) => Number(v)),
    z: zGrid,
    customdata: options.hoverExtra ? customGrid : undefined,
    type: 'heatmap',
    colorscale,
    hovertemplate: hovertemplate + '<extra></extra>',
    colorbar: {
      outlinewidth: 0,
      tickfont: { color: axisColor },
      ...(options.colorbarTitle
        ? { title: { text: options.colorbarTitle, font: { color: axisColor } } }
        : {}),
    },
  } as Partial<PlotData>

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, tickfont: { color: axisColor }, automargin: true },
    yaxis: { title: { text: yTitle }, tickfont: { color: axisColor }, automargin: true },
  }

  return { data: [trace], layout }
}

export function differenceBarChart<T>(
  seriesA: OverlaySeries<T>,
  seriesB: OverlaySeries<T>,
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(seriesA.x)
  const yTitle = options.yTitle ?? `${seriesB.label} minus ${seriesA.label}`
  const axisColor = options.axisColor ?? THEME.text

  const aByX = new Map(seriesA.rows.map((row) => [row[seriesA.x] as unknown as number, row[seriesA.y] as unknown as number]))
  const bByX = new Map(seriesB.rows.map((row) => [row[seriesB.x] as unknown as number, row[seriesB.y] as unknown as number]))
  const commonX = [...aByX.keys()].filter((x) => bByX.has(x)).sort((a, b) => a - b)
  const deltas = commonX.map((x) => bByX.get(x)! - aByX.get(x)!)
  const colors = deltas.map((d) => (d >= 0 ? THEME.positive : THEME.negative))

  const trace: Partial<PlotData> = {
    x: commonX,
    y: deltas,
    type: 'bar',
    marker: { color: colors },
    hovertemplate: `%{x}<br>${yTitle}: %{y:.1f}<extra></extra>`,
  }

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...sharedAxisTheme(axisColor) },
    yaxis: { title: { text: yTitle }, ...sharedAxisTheme(axisColor) },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
  }

  return { data: [trace], layout }
}

export interface DumbbellRow {
  category: string
  before: number
  after: number
}

export interface DumbbellChartOptions {
  height?: number
  xTitle?: string
  yTitle?: string
  paperBgcolor?: string
  plotBgcolor?: string
  axisColor?: string
  beforeLabel?: string
  afterLabel?: string
  valueSuffix?: string
  lowerIsBetter?: boolean
}

export function dumbbellChart(
  rows: DumbbellRow[],
  options: DumbbellChartOptions = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const xTitle = options.xTitle ?? ''
  const yTitle = options.yTitle ?? ''
  const axisColor = options.axisColor ?? THEME.text
  const beforeLabel = options.beforeLabel ?? 'Before'
  const afterLabel = options.afterLabel ?? 'After'
  const valueSuffix = options.valueSuffix ?? ''
  const lowerIsBetter = options.lowerIsBetter ?? true
  const height = options.height ?? Math.max(200, 60 + rows.length * 36)

  const sorted = [...rows].sort((a, b) => Math.abs(b.after - b.before) - Math.abs(a.after - a.before))
  const categories = sorted.map((r) => r.category)

  const shapes = sorted.map((r) => {
    const improved = lowerIsBetter ? r.after <= r.before : r.after >= r.before
    return {
      type: 'line' as const,
      xref: 'x' as const,
      yref: 'y' as const,
      x0: r.before,
      x1: r.after,
      y0: r.category,
      y1: r.category,
      line: { color: improved ? THEME.positive : THEME.negative, width: 3 },
    }
  })

  const beforeTrace: Partial<PlotData> = {
    x: sorted.map((r) => r.before),
    y: categories,
    type: 'scatter',
    mode: 'markers',
    name: beforeLabel,
    marker: { color: THEME.textMuted, size: 10 },
    hovertemplate: `%{y}<br>${beforeLabel}: %{x:.1f}${valueSuffix}<extra></extra>`,
  }

  const afterTrace: Partial<PlotData> = {
    x: sorted.map((r) => r.after),
    y: categories,
    type: 'scatter',
    mode: 'markers',
    name: afterLabel,
    marker: { color: THEME.accentGold, size: 10 },
    hovertemplate: `%{y}<br>${afterLabel}: %{x:.1f}${valueSuffix}<extra></extra>`,
  }

  const axisTheme = sharedAxisTheme(axisColor)

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    showlegend: true,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 120, r: 20, t: 20, b: 40 },
    xaxis: { title: { text: xTitle }, ...axisTheme },
    // categoryarray is reversed relative to `categories`: Plotly renders a
    // categorical y-axis bottom-to-top, so reversing keeps the biggest
    // |delta| (categories[0]) at the TOP of the chart, matching the
    // sort-by-|delta|-descending contract.
    yaxis: { title: { text: yTitle }, type: 'category', categoryorder: 'array', categoryarray: [...categories].reverse(), ...axisTheme },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
    shapes,
  }

  return { data: [beforeTrace, afterTrace], layout }
}

export interface MultiLineSeries<T> {
  y: keyof T & string
  label: string
  color: string
}

export function multiLineChart<T>(
  rows: T[],
  x: keyof T & string,
  series: MultiLineSeries<T>[],
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? ''
  const axisColor = options.axisColor ?? THEME.text

  const data: Partial<PlotData>[] = series.map((s) => ({
    x: rows.map((row) => row[x] as unknown as string | number),
    y: rows.map((row) => row[s.y] as unknown as number),
    type: 'scatter',
    mode: 'lines+markers',
    name: s.label,
    line: { color: s.color, width: 2 },
    marker: { size: 5 },
    hovertemplate: `%{x}<br>${s.label}: %{y:.1f}<extra></extra>`,
  }))

  const axisTheme = sharedAxisTheme(axisColor)

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    showlegend: true,
    paper_bgcolor: options.paperBgcolor ?? THEME.bg,
    plot_bgcolor: options.plotBgcolor ?? THEME.bgSecondary,
    font: { color: axisColor, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...axisTheme },
    yaxis: { title: { text: yTitle }, ...axisTheme },
    hoverlabel: { bgcolor: options.plotBgcolor ?? THEME.bgSecondary, font: { color: axisColor } },
  }

  return { data, layout }
}

export interface AcplTrajectoryPoint {
  year: number
  acpl: number
  n_games: number
  n_total_games: number
  coverage_pct: number
}

export function coverageWarning(rows: AcplTrajectoryPoint[]): string | null {
  if (rows.length < 2) return null
  const minRow = rows.reduce((a, b) => (a.coverage_pct <= b.coverage_pct ? a : b))
  const maxRow = rows.reduce((a, b) => (a.coverage_pct >= b.coverage_pct ? a : b))
  if (maxRow.coverage_pct >= 2 * Math.max(minRow.coverage_pct, 0.1)) {
    return (
      `⚠️ Analysis coverage varies sharply by year — from ` +
      `${minRow.coverage_pct.toFixed(1)}% in ${minRow.year} to ` +
      `${maxRow.coverage_pct.toFixed(1)}% in ${maxRow.year}.`
    )
  }
  return null
}

function endingTreeColor(id: string): string {
  if (id === 'root') return rgba(THEME.text, 0.15)
  const segments = id.split('/')
  const leaf = segments[segments.length - 1]
  if (leaf === 'not_analyzed') return THEME.textMuted
  const branch = segments[0]
  const branchColor = branch === 'win' ? THEME.positive : branch === 'draw' ? THEME.accentGold : THEME.negative
  if (segments.length === 1) return branchColor
  const alpha = segments.length === 2 ? 0.7 : 0.45
  return rgba(branchColor, alpha)
}

function endingTreeLabel(id: string, rawLabel: string): string {
  const leaf = id.split('/').pop() as string
  return END_TYPE_LABELS[leaf] ?? RESIGNATION_REASON_LABELS[leaf] ?? rawLabel
}

export function icicleChart(
  tree: EndingTree,
  options: { height?: number } = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 480

  const trace = {
    type: 'icicle',
    ids: tree.ids,
    labels: tree.ids.map((id, i) => endingTreeLabel(id, tree.labels[i])),
    parents: tree.parents,
    values: tree.values,
    branchvalues: 'total',
    marker: { colors: tree.ids.map(endingTreeColor) },
    textfont: { color: THEME.text, family: CHART_FONT_FAMILY },
    hovertemplate: '%{label}<br>%{value} games<extra></extra>',
  } as unknown as Partial<PlotData>

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: THEME.bg,
    font: { color: THEME.text, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 8, r: 8, t: 8, b: 8 },
  }

  return { data: [trace], layout }
}

export function openingTreeIcicleChart(
  map: OpeningTreeMap,
  options: { height?: number } = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 480
  const labels = map.ids.map((_, i) => (map.has_flip[i] ? `${map.labels[i]} ⚠` : map.labels[i]))

  const trace = {
    type: 'icicle',
    ids: map.ids,
    labels,
    parents: map.parents,
    values: map.values,
    branchvalues: 'total',
    // Reuses THEME.diverging (dashboard/theme.py's DIVERGING_COLORSCALE,
    // already used elsewhere) directly as Plotly's marker.colorscale --
    // icicle/sunburst traces support numeric marker.colors + colorscale
    // exactly like a heatmap, so no separate color-interpolation helper
    // is needed.
    marker: { colors: map.win_pct, colorscale: THEME.diverging, cmin: 0, cmax: 100 },
    textfont: { color: THEME.text, family: CHART_FONT_FAMILY },
    hovertemplate: '%{label}<br>%{value} games<extra></extra>',
  } as unknown as Partial<PlotData>

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: THEME.bg,
    font: { color: THEME.text, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 8, r: 8, t: 8, b: 8 },
  }

  return { data: [trace], layout }
}

export interface SankeyBucketRow {
  bucket: PointsBucketKey
  n_games: number
  leaked: number
}

const SANKEY_BUCKET_ORDER: PointsBucketKey[] = ['failed_conversion', 'missed_swindle', 'failed_hold']

export function sankeyChart(
  buckets: SankeyBucketRow[],
  actualPoints: number,
  leakedPoints: number,
  options: { height?: number } = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 420
  const byBucket = new Map(buckets.map((b) => [b.bucket, b]))
  const present = SANKEY_BUCKET_ORDER.filter((key) => byBucket.has(key))

  const labels = ['All games', 'Kept', 'Leaked', ...present.map((key) => POINTS_BUCKET_LABEL[key])]
  const colors = [rgba(THEME.text, 0.15), THEME.positive, THEME.negative, ...present.map((key) => POINTS_BUCKET_COLOR[key])]
  const nodeCustomdata: Array<PointsBucketKey | null> = [null, null, null, ...present]

  const source = [0, 0, ...present.map(() => 2)]
  const target = [1, 2, ...present.map((_, i) => 3 + i)]
  const value = [actualPoints, leakedPoints, ...present.map((key) => byBucket.get(key)!.leaked)]
  const linkColors = [rgba(THEME.positive, 0.4), rgba(THEME.negative, 0.4), ...present.map((key) => rgba(POINTS_BUCKET_COLOR[key], 0.55))]
  const linkCustomdata: Array<PointsBucketKey | null> = [null, null, ...present]

  const trace = {
    type: 'sankey',
    orientation: 'h',
    node: {
      label: labels,
      color: colors,
      customdata: nodeCustomdata,
      pad: 16,
      thickness: 18,
      line: { color: THEME.bg, width: 1 },
    },
    link: {
      source,
      target,
      value,
      color: linkColors,
      customdata: linkCustomdata,
    },
    textfont: { color: THEME.text, family: CHART_FONT_FAMILY },
  } as unknown as Partial<PlotData>

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: THEME.bg,
    font: { color: THEME.text, size: 13, family: CHART_FONT_FAMILY },
    margin: { l: 8, r: 8, t: 8, b: 8 },
  }

  return { data: [trace], layout }
}

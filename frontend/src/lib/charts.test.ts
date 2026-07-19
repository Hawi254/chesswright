import { describe, expect, it } from 'vitest'
import { barChart, coverageWarning, differenceBarChart, dumbbellChart, groupedBarChart, heatmap, icicleChart, lineChart, multiLineChart, openingTreeIcicleChart, overlayBarChart, sankeyChart, stackedBarChart } from './charts'
import type { DumbbellRow, SankeyBucketRow } from './charts'
import type { EndingTree } from './endingTree'
import type { OpeningTreeMap } from './openingTreeMap'
import { THEME } from './theme'

describe('lineChart', () => {
  const rows = [
    { year: 2024, avg_rating: 1400 },
    { year: 2025, avg_rating: 1500 },
  ]

  it('builds one scatter trace from the given x/y columns', () => {
    const { data } = lineChart(rows, 'year', 'avg_rating', '#C19A4B')
    expect(data).toHaveLength(1)
    expect(data[0].x).toEqual([2024, 2025])
    expect(data[0].y).toEqual([1400, 1500])
    expect(data[0].type).toBe('scatter')
    expect(data[0].mode).toBe('lines+markers')
    expect(data[0].line).toEqual({ color: '#C19A4B', width: 2 })
  })

  it('title-cases axis titles by default', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#C19A4B')
    expect(layout.xaxis?.title).toEqual({ text: 'Year' })
    expect(layout.yaxis?.title).toEqual({ text: 'Avg Rating' })
  })

  it('uses explicit axis titles when given', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#C19A4B', {
      xTitle: 'Year',
      yTitle: 'Average rating',
    })
    expect(layout.xaxis?.title).toEqual({ text: 'Year' })
    expect(layout.yaxis?.title).toEqual({ text: 'Average rating' })
  })

  it('appends a hoverExtra column to the hovertemplate and customdata', () => {
    const coverageRows = [{ year: 2024, acpl: 40, hover_coverage: '5 of 10 games (50.0%)' }]
    const { data } = lineChart(coverageRows, 'year', 'acpl', '#B0584F', {
      hoverExtra: { column: 'hover_coverage', label: 'Analyzed' },
    })
    expect(data[0].customdata).toEqual(['5 of 10 games (50.0%)'])
    expect(data[0].hovertemplate).toContain('Analyzed: %{customdata}')
  })

  it('applies the dark theme colors to the layout', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#C19A4B')
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
    expect(layout.font).toEqual({
      color: '#E8E6E1', size: 13, family: '"Archivo Narrow", "Arial Narrow", sans-serif',
    })
  })

  it('defaults paper/plot/axis colors when no override is given', () => {
    const { layout } = lineChart([{ year: 2024, avg_rating: 1400 }], 'year', 'avg_rating', '#C19A4B')
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
  })

  it('accepts explicit paper/plot/axis color overrides', () => {
    const { layout } = lineChart(
      [{ year: 2024, avg_rating: 1400 }], 'year', 'avg_rating', '#E08A3C',
      { paperBgcolor: '#0B0F14', plotBgcolor: '#0F141B', axisColor: '#ECEEF0' },
    )
    expect(layout.paper_bgcolor).toBe('#0B0F14')
    expect(layout.plot_bgcolor).toBe('#0F141B')
    expect(layout.font).toEqual({
      color: '#ECEEF0', size: 13, family: '"Archivo Narrow", "Arial Narrow", sans-serif',
    })
  })

  it('adds a filled area trace when fill is true', () => {
    const { data } = lineChart(rows, 'year', 'avg_rating', '#E08A3C', { fill: true })
    expect(data[0].fill).toBe('tozeroy')
    expect(data[0].fillcolor).toBe('rgba(224,138,60,0.08)')
  })

  it('omits fill by default', () => {
    const { data } = lineChart(rows, 'year', 'avg_rating', '#E08A3C')
    expect(data[0].fill).toBeUndefined()
  })

  it('adds a reference-line shape when referenceLine is given', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#E08A3C', {
      referenceLine: { y: 0.5, color: '#4FB8C4' },
    })
    expect(layout.shapes).toEqual([
      { type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 0.5, y1: 0.5,
        line: { color: '#4FB8C4', dash: 'dot', width: 1 } },
    ])
  })
})

describe('barChart', () => {
  it('builds a bar trace with the given x/y/color', () => {
    const rows = [
      { year: 2024, n_games: 50 },
      { year: 2025, n_games: 60 },
    ]
    const { data, layout } = barChart(rows, 'year', 'n_games', '#5b6472', { height: 200 })

    expect(data[0].type).toBe('bar')
    expect(data[0].x).toEqual([2024, 2025])
    expect(data[0].y).toEqual([50, 60])
    expect(data[0].marker).toEqual({ color: '#5b6472' })
    expect(layout.height).toBe(200)
  })
})

describe('coverageWarning', () => {
  it('returns null with fewer than 2 rows', () => {
    expect(coverageWarning([])).toBeNull()
    expect(
      coverageWarning([{ year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 }]),
    ).toBeNull()
  })

  it('returns null when coverage does not vary sharply', () => {
    const rows = [
      { year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 },
      { year: 2025, acpl: 42, n_games: 6, n_total_games: 10, coverage_pct: 60 },
    ]
    expect(coverageWarning(rows)).toBeNull()
  })

  it('warns when the max coverage is at least double the min (floor 0.1)', () => {
    const rows = [
      { year: 2024, acpl: 40, n_games: 1, n_total_games: 100, coverage_pct: 1 },
      { year: 2025, acpl: 42, n_games: 50, n_total_games: 100, coverage_pct: 50 },
    ]
    expect(coverageWarning(rows)).toBe(
      '⚠️ Analysis coverage varies sharply by year — from 1.0% in 2024 to 50.0% in 2025.',
    )
  })

  it('uses the first occurrence on a coverage_pct tie, matching pandas idxmin/idxmax', () => {
    const rows = [
      { year: 2024, acpl: 40, n_games: 1, n_total_games: 100, coverage_pct: 10 },
      { year: 2025, acpl: 41, n_games: 1, n_total_games: 10, coverage_pct: 10 },
      { year: 2026, acpl: 42, n_games: 50, n_total_games: 100, coverage_pct: 50 },
    ]
    expect(coverageWarning(rows)).toContain('10.0% in 2024')
  })
})

describe('overlayBarChart', () => {
  const seriesA = {
    rows: [{ move_number: 1, avg_cpl: 10 }, { move_number: 2, avg_cpl: 20 }],
    x: 'move_number' as const, y: 'avg_cpl' as const, label: 'Sicilian Defense (white)', color: '#C19A4B',
  }
  const seriesB = {
    rows: [{ move_number: 1, avg_cpl: 15 }, { move_number: 2, avg_cpl: 5 }],
    x: 'move_number' as const, y: 'avg_cpl' as const, label: "Queen's Gambit (white)", color: '#6FA98C',
  }

  it('builds two grouped bar traces, one per series', () => {
    const { data, layout } = overlayBarChart(seriesA, seriesB)
    expect(data).toHaveLength(2)
    expect(data[0].type).toBe('bar')
    expect(data[0].y).toEqual([10, 20])
    expect(data[0].name).toBe('Sicilian Defense (white)')
    expect(data[1].y).toEqual([15, 5])
    expect(data[1].name).toBe("Queen's Gambit (white)")
    expect(layout.barmode).toBe('group')
  })

  it('colors each trace from its own series', () => {
    const { data } = overlayBarChart(seriesA, seriesB)
    expect(data[0].marker).toEqual({ color: '#C19A4B' })
    expect(data[1].marker).toEqual({ color: '#6FA98C' })
  })
})

describe('groupedBarChart', () => {
  const rows = [
    { piece_name: 'queen', phase: 'opening', blunder_rate: 5 },
    { piece_name: 'queen', phase: 'middlegame', blunder_rate: 10 },
    { piece_name: 'rook', phase: 'opening', blunder_rate: 3 },
    { piece_name: 'rook', phase: 'middlegame', blunder_rate: 8 },
  ]

  it('builds one bar trace per distinct groupCol value, in first-seen order', () => {
    const { data, layout } = groupedBarChart(rows, 'piece_name', 'phase', 'blunder_rate')
    expect(data).toHaveLength(2)
    expect(data[0].name).toBe('opening')
    expect(data[0].x).toEqual(['queen', 'rook'])
    expect(data[0].y).toEqual([5, 3])
    expect(data[1].name).toBe('middlegame')
    expect(data[1].y).toEqual([10, 8])
    expect(layout.barmode).toBe('group')
    expect(layout.showlegend).toBe(true)
  })

  it('assigns default palette colors in series order when no colors override is given', () => {
    const { data } = groupedBarChart(rows, 'piece_name', 'phase', 'blunder_rate')
    expect(data[0].marker).toEqual({ color: '#C19A4B' })
    expect(data[1].marker).toEqual({ color: '#6FA98C' })
  })

  it('looks up each trace color by its groupCol value when colors is given', () => {
    const backrankRows = [
      { piece_name: 'rook', location: 'back rank', acpl: 20 },
      { piece_name: 'rook', location: 'elsewhere', acpl: 60 },
    ]
    const { data } = groupedBarChart(backrankRows, 'piece_name', 'location', 'acpl', {
      colors: { 'back rank': '#6FA98C', elsewhere: '#B0584F' },
    })
    const backRankTrace = data.find((t) => t.name === 'back rank')
    const elsewhereTrace = data.find((t) => t.name === 'elsewhere')
    expect(backRankTrace?.marker).toEqual({ color: '#6FA98C' })
    expect(elsewhereTrace?.marker).toEqual({ color: '#B0584F' })
  })

  it('applies the dark theme colors to the layout', () => {
    const { layout } = groupedBarChart(rows, 'piece_name', 'phase', 'blunder_rate')
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
  })
})

describe('heatmap', () => {
  const cells = [
    { file: 'e', rank: 4, blunder_rate: 20, n_moves_display: '25 moves' },
    { file: 'a', rank: 1, blunder_rate: 5, n_moves_display: '10 moves' },
  ]

  it('pivots long-form cells into a 2D z grid, x sorted ascending and y sorted descending', () => {
    const { data } = heatmap(cells, 'file', 'rank', 'blunder_rate', [[0, '#1E2530'], [1, '#C19A4B']])
    expect(data[0].type).toBe('heatmap')
    expect(data[0].x).toEqual(['a', 'e'])
    expect(data[0].y).toEqual([4, 1])
    expect(data[0].z).toEqual([
      [null, 20],
      [5, null],
    ])
  })

  it('passes the colorscale through unchanged', () => {
    const { data } = heatmap(cells, 'file', 'rank', 'blunder_rate', [[0, '#1E2530'], [1, '#C19A4B']])
    expect(data[0].colorscale).toEqual([[0, '#1E2530'], [1, '#C19A4B']])
  })

  it('builds a 2D customdata grid and appends hoverExtra to the hovertemplate when given', () => {
    const { data } = heatmap(cells, 'file', 'rank', 'blunder_rate', [[0, '#1E2530'], [1, '#C19A4B']], {
      hoverExtra: { column: 'n_moves_display', label: 'Sample size' },
    })
    expect(data[0].customdata).toEqual([
      [null, '25 moves'],
      ['10 moves', null],
    ])
    expect(data[0].hovertemplate).toContain('Sample size: %{customdata}')
  })

  it('omits customdata when no hoverExtra is given', () => {
    const { data } = heatmap(cells, 'file', 'rank', 'blunder_rate', [[0, '#1E2530'], [1, '#C19A4B']])
    expect(data[0].customdata).toBeUndefined()
  })

  it('applies the dark theme colors to the layout', () => {
    const { layout } = heatmap(cells, 'file', 'rank', 'blunder_rate', [[0, '#1E2530'], [1, '#C19A4B']])
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
    expect(layout.height).toBe(380)
  })

  it('uses xOrder/yOrder verbatim when given, keeping y as strings (not Number-coerced)', () => {
    const dayHourCells = [
      { hour_local: 1, day: 'Tue', win_pct: 60 },
      { hour_local: 23, day: 'Mon', win_pct: 40 },
    ]
    const { data } = heatmap(dayHourCells, 'hour_local', 'day', 'win_pct',
      [[0, '#B0584F'], [0.5, '#1E2530'], [1, '#6FA98C']],
      {
        xOrder: Array.from({ length: 24 }, (_, i) => String(i)),
        yOrder: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      })
    expect(data[0].x).toHaveLength(24)
    expect(data[0].x?.[1]).toBe('1')
    expect(data[0].x?.[23]).toBe('23')
    expect(data[0].y).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
    const z = data[0].z as Array<Array<number | null>>
    expect(z[0][23]).toBe(40)  // Mon row, hour 23 column
    expect(z[1][1]).toBe(60)   // Tue row, hour 1 column
  })

  it('leaves the pre-existing numeric-descending y / lexicographic x behavior unchanged when no order options are given', () => {
    const { data } = heatmap(cells, 'file', 'rank', 'blunder_rate', [[0, '#1E2530'], [1, '#C19A4B']])
    expect(data[0].x).toEqual(['a', 'e'])
    expect(data[0].y).toEqual([4, 1])
    expect(typeof data[0].y?.[0]).toBe('number')
  })
})

describe('differenceBarChart', () => {
  it('subtracts seriesA from seriesB over the intersecting x-values only', () => {
    const seriesA = {
      rows: [{ move_number: 1, avg_cpl: 10 }, { move_number: 2, avg_cpl: 20 }, { move_number: 3, avg_cpl: 30 }],
      x: 'move_number' as const, y: 'avg_cpl' as const, label: 'A', color: '#C19A4B',
    }
    const seriesB = {
      rows: [{ move_number: 1, avg_cpl: 15 }, { move_number: 2, avg_cpl: 5 }],
      x: 'move_number' as const, y: 'avg_cpl' as const, label: 'B', color: '#6FA98C',
    }
    const { data } = differenceBarChart(seriesA, seriesB)
    expect(data).toHaveLength(1)
    expect(data[0].x).toEqual([1, 2])  // move_number 3 dropped -- not in seriesB
    expect(data[0].y).toEqual([5, -15])  // 15-10, 5-20
  })

  it('colors positive deltas THEME.positive and negative deltas THEME.negative', () => {
    const seriesA = {
      rows: [{ move_number: 1, avg_cpl: 10 }, { move_number: 2, avg_cpl: 20 }],
      x: 'move_number' as const, y: 'avg_cpl' as const, label: 'A', color: '#C19A4B',
    }
    const seriesB = {
      rows: [{ move_number: 1, avg_cpl: 15 }, { move_number: 2, avg_cpl: 5 }],
      x: 'move_number' as const, y: 'avg_cpl' as const, label: 'B', color: '#6FA98C',
    }
    const { data } = differenceBarChart(seriesA, seriesB)
    expect((data[0].marker as { color: string[] }).color).toEqual(['#6FA98C', '#B0584F'])
  })
})

describe('dumbbellChart', () => {
  const rows: DumbbellRow[] = [
    { category: 'opening', before: 20, after: 18 },     // |delta| 2, improved
    { category: 'middlegame', before: 30, after: 45 },  // |delta| 15, regressed
    { category: 'endgame', before: 10, after: 10 },     // |delta| 0, unchanged
  ]

  it('sorts categories by |delta| descending', () => {
    const chart = dumbbellChart(rows)
    expect(chart.data[0].y).toEqual(['middlegame', 'opening', 'endgame'])
  })

  it('builds a before trace and an after trace with matching x values', () => {
    const chart = dumbbellChart(rows)
    expect(chart.data).toHaveLength(2)
    expect(chart.data[0].x).toEqual([30, 20, 10])   // before, sorted
    expect(chart.data[1].x).toEqual([45, 18, 10])   // after, sorted
    expect(chart.data[0].mode).toBe('markers')
    expect(chart.data[1].mode).toBe('markers')
  })

  it('colors the connecting shape green when after improves on before (lower is better)', () => {
    const chart = dumbbellChart(rows)
    const shapes = chart.layout.shapes as Array<{ x0: number; x1: number; line: { color: string } }>
    const openingShape = shapes[1]  // opening is index 1 in sorted order
    expect(openingShape.x0).toBe(20)
    expect(openingShape.x1).toBe(18)
    expect(openingShape.line.color).toBe(THEME.positive)
  })

  it('colors the connecting shape red when after regresses from before', () => {
    const chart = dumbbellChart(rows)
    const shapes = chart.layout.shapes as Array<{ line: { color: string } }>
    const middlegameShape = shapes[0]  // middlegame is index 0 (biggest |delta|)
    expect(middlegameShape.line.color).toBe(THEME.negative)
  })

  it('returns an empty chart for zero rows without throwing', () => {
    const chart = dumbbellChart([])
    expect(chart.data[0].x).toEqual([])
    expect(chart.data[0].y).toEqual([])
  })
})

describe('multiLineChart', () => {
  const rows = [
    { label: 'Q1 2025', pct_upset: 10, pct_collapse: 5 },
    { label: 'Q2 2025', pct_upset: 15, pct_collapse: 8 },
  ]

  it('builds one scatter trace per series, in order', () => {
    const { data } = multiLineChart(rows, 'label', [
      { y: 'pct_upset', label: 'Upset win rate', color: '#6FA98C' },
      { y: 'pct_collapse', label: 'Collapse loss rate', color: '#B0584F' },
    ])
    expect(data).toHaveLength(2)
    expect(data[0].name).toBe('Upset win rate')
    expect(data[0].x).toEqual(['Q1 2025', 'Q2 2025'])
    expect(data[0].y).toEqual([10, 15])
    expect(data[0].line).toEqual({ color: '#6FA98C', width: 2 })
    expect(data[1].name).toBe('Collapse loss rate')
    expect(data[1].y).toEqual([5, 8])
  })

  it('enables the legend so the two series are distinguishable', () => {
    const { layout } = multiLineChart(rows, 'label', [
      { y: 'pct_upset', label: 'Upset win rate', color: '#6FA98C' },
    ])
    expect(layout.showlegend).toBe(true)
  })

  it('applies the dark theme colors to the layout', () => {
    const { layout } = multiLineChart(rows, 'label', [
      { y: 'pct_upset', label: 'Upset win rate', color: '#6FA98C' },
    ])
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
  })
})

const TREE: EndingTree = {
  ids: ['root', 'win', 'loss', 'loss/checkmate', 'loss/resignation', 'loss/resignation/hung_piece', 'loss/resignation/not_analyzed'],
  labels: ['All games', 'Win', 'Loss', 'checkmate', 'resignation', 'hung_piece', 'not_analyzed'],
  parents: ['', 'root', 'root', 'loss', 'loss', 'loss/resignation', 'loss/resignation'],
  values: [10, 4, 6, 2, 4, 3, 1],
}

describe('icicleChart', () => {
  it('produces one icicle trace with matching ids/parents/values', () => {
    const { data } = icicleChart(TREE)
    expect(data).toHaveLength(1)
    expect(data[0].type).toBe('icicle')
    expect(data[0].ids).toEqual(TREE.ids)
    expect(data[0].parents).toEqual(TREE.parents)
    expect(data[0].values).toEqual(TREE.values)
  })

  it('relabels end-type and resignation-reason slugs via the ported label constants', () => {
    const { data } = icicleChart(TREE)
    const labels = data[0].labels as string[]
    expect(labels[TREE.ids.indexOf('loss/checkmate')]).toBe('Checkmate')
    expect(labels[TREE.ids.indexOf('loss/resignation/hung_piece')]).toBe('Hung a piece')
    expect(labels[TREE.ids.indexOf('loss/resignation/not_analyzed')]).toBe('Not yet analyzed')
    expect(labels[TREE.ids.indexOf('win')]).toBe('Win')
  })

  it('gives every "not_analyzed" leaf the muted color regardless of branch', () => {
    const { data } = icicleChart(TREE)
    const colors = (data[0].marker as { colors: string[] }).colors
    expect(colors[TREE.ids.indexOf('loss/resignation/not_analyzed')]).toBe('rgb(232 230 225 / 0.6)')
  })
})

const OPENING_MAP: OpeningTreeMap = {
  ids: ['root', 'e4', 'e4/e5'],
  labels: ['Start', 'e4', 'e5'],
  parents: ['', 'root', 'e4'],
  values: [10, 8, 5],
  win_pct: [50, 62.5, 40],
  has_flip: [false, false, true],
}

describe('openingTreeIcicleChart', () => {
  it('produces one icicle trace with matching ids/parents/values', () => {
    const { data } = openingTreeIcicleChart(OPENING_MAP)
    expect(data).toHaveLength(1)
    expect(data[0].type).toBe('icicle')
    expect(data[0].ids).toEqual(OPENING_MAP.ids)
    expect(data[0].parents).toEqual(OPENING_MAP.parents)
    expect(data[0].values).toEqual(OPENING_MAP.values)
  })

  it('colors by win_pct using the shared diverging colorscale', () => {
    const { data } = openingTreeIcicleChart(OPENING_MAP)
    const marker = data[0].marker as { colors: number[]; colorscale: unknown; cmin: number; cmax: number }
    expect(marker.colors).toEqual(OPENING_MAP.win_pct)
    expect(marker.cmin).toBe(0)
    expect(marker.cmax).toBe(100)
  })

  it('appends a badge suffix to flipped node labels only', () => {
    const { data } = openingTreeIcicleChart(OPENING_MAP)
    const labels = data[0].labels as string[]
    expect(labels[OPENING_MAP.ids.indexOf('e4/e5')]).toBe('e5 ⚠')
    expect(labels[OPENING_MAP.ids.indexOf('e4')]).toBe('e4')
  })
})

describe('sankeyChart', () => {
  const buckets: SankeyBucketRow[] = [
    { bucket: 'failed_conversion', n_games: 5, leaked: 12 },
    { bucket: 'failed_hold', n_games: 2, leaked: 1 },
  ]

  it('builds one sankey trace with Root->Kept/Leaked plus Leaked->bucket links', () => {
    const { data } = sankeyChart(buckets, 40, 13)
    expect(data).toHaveLength(1)
    const trace = data[0] as unknown as { type: string; node: { label: string[] }; link: { source: number[]; target: number[]; value: number[] } }
    expect(trace.type).toBe('sankey')
    expect(trace.node.label).toEqual(['All games', 'Kept', 'Leaked', 'Failed conversion', 'Failed hold'])
    expect(trace.link.source).toEqual([0, 0, 2, 2])
    expect(trace.link.target).toEqual([1, 2, 3, 4])
    expect(trace.link.value).toEqual([40, 13, 12, 1])
  })

  it('omits a bucket entirely (node + link), not just as a zero-valued node, when absent from the input', () => {
    const { data } = sankeyChart([{ bucket: 'missed_swindle', n_games: 3, leaked: 4 }], 40, 4)
    const trace = data[0] as unknown as { node: { label: string[] }; link: { target: number[] } }
    expect(trace.node.label).toEqual(['All games', 'Kept', 'Leaked', 'Missed swindle'])
    expect(trace.link.target).toEqual([1, 2, 3])
  })

  it('tags each bucket node and its incoming link with the raw bucket key, leaving root/kept/leaked untagged', () => {
    const { data } = sankeyChart(buckets, 40, 13)
    const trace = data[0] as unknown as { node: { customdata: unknown[] }; link: { customdata: unknown[] } }
    expect(trace.node.customdata).toEqual([null, null, null, 'failed_conversion', 'failed_hold'])
    expect(trace.link.customdata).toEqual([null, null, 'failed_conversion', 'failed_hold'])
  })

  it('always orders present buckets failed_conversion, missed_swindle, failed_hold regardless of input order', () => {
    const { data } = sankeyChart(
      [{ bucket: 'failed_hold', n_games: 1, leaked: 1 }, { bucket: 'failed_conversion', n_games: 1, leaked: 5 }],
      40, 6,
    )
    const trace = data[0] as unknown as { node: { label: string[] } }
    expect(trace.node.label.slice(3)).toEqual(['Failed conversion', 'Failed hold'])
  })

  it('gives each present bucket node a distinct color from POINTS_BUCKET_COLOR', () => {
    const { data } = sankeyChart(buckets, 40, 13)
    const trace = data[0] as unknown as { node: { color: string[] } }
    expect(new Set(trace.node.color.slice(3)).size).toBe(2)
  })
})

describe('stackedBarChart', () => {
  const rows = [
    { label: '2018 Q1', family: 'A', share: 60 },
    { label: '2018 Q1', family: 'B', share: 40 },
    { label: '2018 Q2', family: 'A', share: 30 },
    { label: '2018 Q2', family: 'B', share: 70 },
  ]
  const colors = { A: '#3987e5', B: '#c98500' }

  it('builds one bar trace per distinct groupCol value, in first-seen order', () => {
    const { data, layout } = stackedBarChart(rows, 'label', 'family', 'share', colors)
    expect(data).toHaveLength(2)
    expect(data[0].name).toBe('A')
    expect(data[0].x).toEqual(['2018 Q1', '2018 Q2'])
    expect(data[0].y).toEqual([60, 30])
    expect(data[1].name).toBe('B')
    expect(layout.barmode).toBe('stack')
    expect(layout.showlegend).toBe(true)
  })

  it('assigns each trace its color from the required colors map', () => {
    const { data } = stackedBarChart(rows, 'label', 'family', 'share', colors)
    expect((data[0].marker as { color: string }).color).toBe('#3987e5')
    expect((data[1].marker as { color: string }).color).toBe('#c98500')
  })

  it('draws a background-colored gap line between stacked segments', () => {
    const { data } = stackedBarChart(rows, 'label', 'family', 'share', colors)
    expect((data[0].marker as { line: { color: string; width: number } }).line).toEqual({
      color: '#14181F', width: 2,
    })
  })

  it('throws when a group value has no entry in the colors map', () => {
    expect(() => stackedBarChart(rows, 'label', 'family', 'share', { A: '#3987e5' }))
      .toThrow('no color provided for group "B"')
  })

  it('applies the dark theme colors to the layout', () => {
    const { layout } = stackedBarChart(rows, 'label', 'family', 'share', colors)
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
  })
})

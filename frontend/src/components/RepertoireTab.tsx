import { useMemo, useState } from 'react'
import type { RepertoireRow } from '../hooks/useOpponentPrepReport'

type SortColumn = 'opening' | 'color' | 'n_games' | 'score_pct' | 'avg_cpl' | 'blunder_pct'

const COLUMNS: Array<{ key: SortColumn; label: string }> = [
  { key: 'opening', label: 'Opening' },
  { key: 'color', label: 'Color' },
  { key: 'n_games', label: 'Games' },
  { key: 'score_pct', label: 'Score %' },
  { key: 'avg_cpl', label: 'ACPL' },
  { key: 'blunder_pct', label: 'Blunder %' },
]

function IntensityBar({ pct, max, tone }: { pct: number; max: number; tone: 'copper' | 'negative' }) {
  const width = max > 0 ? (pct / max) * 100 : 0
  return (
    <div
      data-testid="intensity-bar"
      className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--cw-line)]"
    >
      <div
        className={tone === 'negative' ? 'h-full bg-negative' : 'h-full bg-[var(--cw-copper)]'}
        style={{ width: `${width}%` }}
      />
    </div>
  )
}

export interface RepertoireTabProps {
  repertoire: RepertoireRow[]
}

export default function RepertoireTab({ repertoire }: RepertoireTabProps) {
  const [sortColumn, setSortColumn] = useState<SortColumn>('n_games')
  const [sortDesc, setSortDesc] = useState(true)

  const sorted = useMemo(() => {
    const rows = [...repertoire]
    rows.sort((a, b) => {
      const av = a[sortColumn]
      const bv = b[sortColumn]
      if (av === bv) return 0
      if (av === null) return 1
      if (bv === null) return -1
      const cmp = av < bv ? -1 : 1
      return sortDesc ? -cmp : cmp
    })
    return rows
  }, [repertoire, sortColumn, sortDesc])

  const maxScore = Math.max(...repertoire.map((r) => r.score_pct), 1)
  const maxBlunder = Math.max(...repertoire.map((r) => r.blunder_pct ?? 0), 1)

  function toggleSort(col: SortColumn) {
    if (col === sortColumn) {
      setSortDesc((prev) => !prev)
    } else {
      setSortColumn(col)
      setSortDesc(true)
    }
  }

  return (
    <table className="mt-3 w-full border-collapse text-left text-xs">
      <thead>
        <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
          {COLUMNS.map((col) => (
            <th key={col.key} scope="col" className="cursor-pointer py-2 pr-3" onClick={() => toggleSort(col.key)}>
              {col.label}{sortColumn === col.key ? (sortDesc ? ' ▼' : ' ▲') : ''}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => (
          <tr key={`${r.opening}|${r.color}`} className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
            <td className="py-2 pr-3">{r.opening}</td>
            <td className="py-2 pr-3 capitalize">{r.color}</td>
            <td className="py-2 pr-3">{r.n_games}</td>
            <td className="py-2 pr-3">
              <div className="flex items-center gap-2">
                <IntensityBar pct={r.score_pct} max={maxScore} tone="copper" />
                {r.score_pct.toFixed(1)}
              </div>
            </td>
            <td className="py-2 pr-3">{r.avg_cpl === null ? '--' : r.avg_cpl.toFixed(1)}</td>
            <td className="py-2 pr-3">
              {r.blunder_pct === null ? '--' : (
                <div className="flex items-center gap-2">
                  <IntensityBar pct={r.blunder_pct} max={maxBlunder} tone="negative" />
                  {r.blunder_pct.toFixed(1)}
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

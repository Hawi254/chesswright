import { useMemo, useState } from 'react'
import Slider from './ui/Slider'
import { useOpeningsTable } from '../hooks/useOpeningsTable'
import { useOpeningNarrative } from '../hooks/useOpeningNarrative'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'

type SortColumn = 'opening_family' | 'player_color' | 'n' | 'win_pct' | 'draw_pct' | 'acpl'

function WinDrawLossBar({ winPct, drawPct }: { winPct: number; drawPct: number }) {
  const lossPct = Math.max(0, 100 - winPct - drawPct)
  return (
    <div className="flex h-1.5 w-24 overflow-hidden rounded-full bg-[var(--cw-line)]">
      <div className="h-full bg-[var(--color-positive)]" style={{ width: `${winPct}%` }} title={`Win ${winPct.toFixed(1)}%`} />
      <div className="h-full bg-[var(--cw-muted)]" style={{ width: `${drawPct}%` }} title={`Draw ${drawPct.toFixed(1)}%`} />
      <div className="h-full bg-negative" style={{ width: `${lossPct}%` }} title={`Loss ${lossPct.toFixed(1)}%`} />
    </div>
  )
}

const COLUMNS: Array<{ key: SortColumn; label: string }> = [
  { key: 'opening_family', label: 'Opening' },
  { key: 'player_color', label: 'Color' },
  { key: 'n', label: 'Games' },
]

export default function OpeningsTableSection() {
  const { openings, loading, error } = useOpeningsTable()
  const [minGames, setMinGames] = useState(5)
  const [search, setSearch] = useState('')
  const [sortColumn, setSortColumn] = useState<SortColumn>('n')
  const [sortDesc, setSortDesc] = useState(true)
  const [selected, setSelected] = useState<{ family: string; color: string } | null>(null)
  const narrative = useOpeningNarrative(selected?.family ?? null, selected?.color ?? null)
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()

  const filtered = useMemo(() => {
    if (!openings) return []
    let rows = openings.filter((r) => r.n >= minGames)
    if (search) {
      const needle = search.toLowerCase()
      rows = rows.filter((r) => r.opening_family.toLowerCase().includes(needle))
    }
    const sorted = [...rows].sort((a, b) => {
      const av = a[sortColumn]
      const bv = b[sortColumn]
      if (av === bv) return 0
      const cmp = av! < bv! ? -1 : 1
      return sortDesc ? -cmp : cmp
    })
    return sorted
  }, [openings, minGames, search, sortColumn, sortDesc])

  function toggleSort(col: SortColumn) {
    if (col === sortColumn) {
      setSortDesc((prev) => !prev)
    } else {
      setSortColumn(col)
      setSortDesc(true)
    }
  }

  if (loading || error || !openings) return null

  const nUnanalyzed = filtered.filter((r) => r.n_analyzed === 0).length
  const selectedRow = selected
    ? filtered.find((r) => r.opening_family === selected.family && r.player_color === selected.color)
    : null

  return (
    <div className="grid grid-cols-[1fr_minmax(280px,360px)] gap-4">
      <div>
        <div className="flex flex-wrap items-end gap-4">
          <label className="block text-xs text-[var(--cw-muted)]">
            Opening name contains
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="mt-1 block w-48 rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-2 py-1 text-[var(--cw-text)]"
            />
          </label>
          <div className="w-48">
            <Slider id="openings-min-games" label="Minimum games" min={1} max={50} value={minGames} onChange={setMinGames} />
          </div>
        </div>
        {nUnanalyzed > 0 && (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">
            ACPL is blank for {nUnanalyzed} of {filtered.length} openings above — no analyzed games
            have reached them yet, not a data error.
          </p>
        )}
        <table className="mt-3 w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              {COLUMNS.map((col) => (
                <th key={col.key} scope="col" className="cursor-pointer py-2 pr-3" onClick={() => toggleSort(col.key)}>
                  {col.label}{sortColumn === col.key ? (sortDesc ? ' ▼' : ' ▲') : ''}
                </th>
              ))}
              <th scope="col" className="py-2 pr-3">Win / Draw / Loss</th>
              <th scope="col" className="py-2">ACPL</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr
                key={`${r.opening_family}|${r.player_color}`}
                onClick={() => setSelected({ family: r.opening_family, color: r.player_color })}
                className="cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)]"
              >
                <td className="py-2 pr-3">{r.opening_family}</td>
                <td className="py-2 pr-3 capitalize">{r.player_color}</td>
                <td className="py-2 pr-3">{r.n}</td>
                <td className="py-2 pr-3"><WinDrawLossBar winPct={r.win_pct} drawPct={r.draw_pct} /></td>
                <td className="py-2">{r.acpl === null ? '--' : r.acpl.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedRow && (
        <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4 text-xs text-[var(--cw-text)]">
          <h3 className="font-condensed text-sm">{selectedRow.opening_family} ({selectedRow.player_color})</h3>
          <p className="mt-1 text-[var(--cw-muted)]">
            {selectedRow.n} games, {selectedRow.win_pct.toFixed(1)}% win, {selectedRow.draw_pct.toFixed(1)}% draw,
            ACPL {selectedRow.acpl === null ? '--' : selectedRow.acpl.toFixed(1)}
          </p>
          {narrative.narrative && (
            <>
              {narrative.generatedAt && <p className="mt-3 text-[var(--cw-muted)]">Generated {narrative.generatedAt}</p>}
              <p className="mt-1">{narrative.narrative}</p>
            </>
          )}
          {!claudeKeyAvailable && (
            <p className="mt-3 text-[var(--cw-muted)]">Add your own Anthropic API key on the Settings page to enable this.</p>
          )}
          <button
            type="button"
            disabled={!claudeKeyAvailable || narrative.generating}
            onClick={() => narrative.generate()}
            className="mt-3 rounded border border-[var(--cw-copper)] px-3 py-1.5 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
          >
            {narrative.narrative ? 'Regenerate commentary' : 'Generate commentary'}
          </button>
          {narrative.generateError && <p className="mt-2 text-negative">{narrative.generateError}</p>}
        </div>
      )}
    </div>
  )
}

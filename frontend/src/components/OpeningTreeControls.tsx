import { useEffect, useMemo, useState } from 'react'
import { API_BASE } from '../lib/apiBase'
import { useOpeningJump } from '../hooks/useOpeningJump'
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from './ui/command'

interface OpeningRow {
  opening_family: string
  player_color: string
}

export default function OpeningTreeControls({
  color, onColorChange, minGames, onMinGamesChange, onJumpToPath,
}: {
  color: 'w' | 'b'
  onColorChange: (color: 'w' | 'b') => void
  minGames: number
  onMinGamesChange: (minGames: number) => void
  onJumpToPath: (path: string[]) => void
}) {
  const [families, setFamilies] = useState<string[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const { jump, path, status } = useOpeningJump(color)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/openings/table`)
      .then((r) => (r.ok ? (r.json() as Promise<OpeningRow[]>) : []))
      .then((rows) => {
        if (cancelled) return
        const dbColor = color === 'w' ? 'white' : 'black'
        const unique = Array.from(new Set(rows.filter((r) => r.player_color === dbColor).map((r) => r.opening_family)))
        setFamilies(unique.sort())
      })
      .catch(() => { if (!cancelled) setFamilies([]) })
    return () => { cancelled = true }
  }, [color])

  useEffect(() => {
    if (status === 'ok' && path) {
      onJumpToPath(path)
      setSearchOpen(false)
    }
  }, [status, path, onJumpToPath])

  const label = useMemo(() => (color === 'w' ? 'White' : 'Black'), [color])

  return (
    <div className="flex items-center gap-4 border-b border-[var(--cw-line)] p-3">
      <div className="flex gap-1">
        <button type="button" onClick={() => onColorChange('w')}
          aria-pressed={color === 'w'}
          className={`rounded px-2 py-1 text-xs ${color === 'w' ? 'bg-[var(--cw-copper)] text-black' : 'text-[var(--cw-text)]'}`}>
          White
        </button>
        <button type="button" onClick={() => onColorChange('b')}
          aria-pressed={color === 'b'}
          className={`rounded px-2 py-1 text-xs ${color === 'b' ? 'bg-[var(--cw-copper)] text-black' : 'text-[var(--cw-text)]'}`}>
          Black
        </button>
      </div>
      <label className="flex items-center gap-2 text-xs text-[var(--cw-muted)]">
        Min games
        <input type="range" role="slider" min={1} max={20} value={minGames}
          onChange={(e) => onMinGamesChange(Number(e.target.value))} />
        <span>{minGames}</span>
      </label>
      <button type="button" onClick={() => setSearchOpen(true)}
        className="ml-auto rounded border border-[var(--cw-line)] px-2 py-1 text-xs text-[var(--cw-muted)]">
        Jump to an opening…
      </button>
      <CommandDialog open={searchOpen} onOpenChange={setSearchOpen}>
        <CommandInput placeholder="Jump to an opening…" />
        <CommandList>
          <CommandEmpty>
            {status === 'not_found' ? `No ${label.toLowerCase()} games found for this opening.` : 'No results found.'}
          </CommandEmpty>
          <CommandGroup heading="Openings">
            {families.map((family) => (
              <CommandItem key={family} value={family} onSelect={() => jump(family)}>
                {family}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </div>
  )
}

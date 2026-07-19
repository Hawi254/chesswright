import { useState } from 'react'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './ui/command'

export interface OpponentPrepSearchBoxProps {
  knownOpponents: string[]
  onLoadKnown: (username: string) => void
  onScoutNew: (username: string, nGames: number) => void
}

export default function OpponentPrepSearchBox({
  knownOpponents, onLoadKnown, onScoutNew,
}: OpponentPrepSearchBoxProps) {
  const [query, setQuery] = useState('')
  const [nGames, setNGames] = useState(50)

  const matches = knownOpponents.filter((name) => name.toLowerCase().includes(query.toLowerCase()))
  const isKnown = knownOpponents.some((name) => name.toLowerCase() === query.toLowerCase())
  const trimmed = query.trim()

  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)]">
      <Command>
        <CommandInput
          placeholder="Enter a lichess username..."
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          {matches.length > 0 && (
            <CommandGroup heading="Previously scouted">
              {matches.map((name) => (
                <CommandItem key={name} value={name} onSelect={() => onLoadKnown(name)}>
                  {name}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {trimmed && !isKnown && (
            <CommandGroup heading="Scout a new opponent">
              <CommandItem value={`scout-${trimmed}`} onSelect={() => onScoutNew(trimmed, nGames)}>
                {`Scout ${trimmed}`}
              </CommandItem>
            </CommandGroup>
          )}
          {!trimmed && <CommandEmpty>Enter a lichess username to search or scout.</CommandEmpty>}
        </CommandList>
      </Command>
      {trimmed && !isKnown && (
        <label className="flex items-center gap-2 border-t border-[var(--cw-line)] p-2 text-xs text-[var(--cw-muted)]">
          Games to fetch
          <input
            type="number"
            min={10}
            max={200}
            step={10}
            value={nGames}
            onChange={(e) => setNGames(Number(e.target.value))}
            className="w-16 rounded border border-[var(--cw-line)] bg-[var(--cw-canvas)] px-1 py-0.5 text-[var(--cw-text)]"
          />
        </label>
      )}
    </div>
  )
}

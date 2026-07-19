import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './ui/command'

export default function OpponentPicker({
  opponents, onSelect,
}: {
  opponents: string[]
  onSelect: (opponentName: string) => void
}) {
  return (
    <Command className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)]">
      <CommandInput placeholder="Find an opponent by name…" />
      <CommandList>
        <CommandEmpty>No opponents found.</CommandEmpty>
        <CommandGroup heading="All opponents">
          {opponents.map((name) => (
            <CommandItem key={name} value={name} onSelect={() => onSelect(name)}>
              {name}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </Command>
  )
}

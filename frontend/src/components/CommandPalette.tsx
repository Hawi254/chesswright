import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command'
import type { PageCandidate } from '../lib/navCandidates'

export interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  candidates: PageCandidate[]
}

export default function CommandPalette({ open, onOpenChange, candidates }: CommandPaletteProps) {
  const navigate = useNavigate()

  useEffect(() => {
    // Registered on `document`, not scoped to any component inside the
    // palette itself -- this is the specific thing that must work
    // regardless of where focus currently is, the exact case Streamlit's
    // iframe-sandboxed custom components can't do (BRIEF §25).
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onOpenChange])

  function handleSelect(urlPath: string, anchor?: string) {
    navigate(anchor ? `/${urlPath}#${anchor}` : `/${urlPath}`)
    onOpenChange(false)
  }

  const pages = useMemo(() => candidates.filter((c) => c.category === 'page'), [candidates])
  const settings = useMemo(() => candidates.filter((c) => c.category === 'setting'), [candidates])

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search pages, settings…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Pages">
          {pages.map((page) => (
            <CommandItem
              key={page.url_path}
              value={page.title}
              onSelect={() => handleSelect(page.url_path)}
            >
              {page.title}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Settings">
          {settings.map((setting) => (
            <CommandItem
              key={`${setting.url_path}#${setting.anchor ?? ''}`}
              // "Settings " prefix (not shown -- only {setting.title} is
              // rendered below) so every settings-category entry is
              // findable by searching the group name itself, e.g.
              // "Anthropic API key" alone has no fuzzy-matchable relation
              // to the query "Settings" (it doesn't even contain an 's').
              // Found live while verifying Task 7's Step 3.7.
              value={`Settings ${setting.title}`}
              onSelect={() => handleSelect(setting.url_path, setting.anchor)}
            >
              {setting.title}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}

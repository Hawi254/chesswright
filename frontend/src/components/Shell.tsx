import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import CommandPalette from './CommandPalette'
import Logo from './Logo'
import { usePageCandidates } from '../hooks/usePageCandidates'

export default function Shell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { candidates } = usePageCandidates()

  return (
    <div className="flex h-screen bg-[var(--cw-canvas)] text-[var(--cw-text)]">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-[var(--cw-line)] px-6">
          <Logo />
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-2 rounded border border-[var(--cw-line)] px-3 py-1.5 text-sm text-[var(--cw-muted)] hover:border-[var(--cw-copper)]/50 hover:text-[var(--cw-text)]"
          >
            Search…
            <kbd className="rounded border border-[var(--cw-copper)]/40 px-1.5 py-0.5 font-mono text-[10px] text-[var(--cw-copper)]">
              ⌘K
            </kbd>
          </button>
        </header>
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} candidates={candidates} />
    </div>
  )
}

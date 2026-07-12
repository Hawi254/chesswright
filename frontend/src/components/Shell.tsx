import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import CommandPalette from './CommandPalette'
import { usePageCandidates } from '../hooks/usePageCandidates'

export default function Shell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { candidates } = usePageCandidates()

  return (
    <div className="flex h-screen bg-bg text-text">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-bg-secondary px-6">
          <span className="font-semibold text-accent-gold">Chesswright</span>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="rounded border border-bg-secondary px-3 py-1 text-sm text-text-muted hover:text-text"
          >
            Search… <kbd className="ml-2 text-xs">⌘K</kbd>
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

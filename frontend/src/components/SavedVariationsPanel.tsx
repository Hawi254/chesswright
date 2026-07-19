import type { SavedVariation } from '../hooks/useSavedVariations'
import { API_BASE } from '../lib/apiBase'

export interface SavedVariationsPanelProps {
  variations: SavedVariation[]
  onLoad: (variation: SavedVariation) => void
  onDelete: (variationId: string) => void
}

export default function SavedVariationsPanel({ variations, onLoad, onDelete }: SavedVariationsPanelProps) {
  if (variations.length === 0) return null

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <p className="font-condensed text-xs uppercase text-[var(--cw-muted)]">Saved variations</p>
      <ul className="mt-2 flex flex-col gap-2">
        {variations.map((variation) => {
          const branchMoveNumber = Math.floor((variation.branch_ply + 1) / 2)
          const title = variation.title ?? `From move ${branchMoveNumber}`
          const n = variation.moves.length
          return (
            <li key={variation.id} className="flex items-center justify-between gap-2">
              <span className="font-condensed text-xs text-[var(--cw-text)]">
                <strong>{title}</strong> — {n} move{n !== 1 ? 's' : ''}, branching at move{' '}
                {branchMoveNumber}
              </span>
              <span className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={() => onLoad(variation)}
                  className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
                >
                  Load
                </button>
                <a
                  href={`${API_BASE}/api/variations/${variation.id}/pgn`}
                  download
                  className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
                >
                  PGN ↓
                </a>
                <button
                  type="button"
                  onClick={() => onDelete(variation.id)}
                  className="rounded border border-negative px-2 py-1 font-condensed text-xs text-negative"
                >
                  Delete
                </button>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

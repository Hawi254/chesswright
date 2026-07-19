import type { HighlightCategory, HighlightCounts } from '../hooks/useTacticalHighlightsReel'
import { TONE_CLASSES } from '../lib/badges'

const CATEGORY_LABELS: Record<HighlightCategory, string> = {
  brilliant: 'Brilliant',
  puzzle_conversion: 'Puzzle conversion',
  best_move_streak: 'Best-move streak',
  blown_mate: 'Blown mate',
  great_escape: 'Great escape',
}

const CATEGORIES = Object.keys(CATEGORY_LABELS) as HighlightCategory[]

export default function HighlightCategoryFilter({
  counts,
  activeCategory,
  onSelect,
}: {
  counts: HighlightCounts
  activeCategory: 'all' | HighlightCategory
  onSelect: (category: 'all' | HighlightCategory) => void
}) {
  const totalCount = Object.values(counts).reduce((sum, n) => sum + n, 0)

  function chipClass(isActive: boolean) {
    return `rounded px-2.5 py-1 font-condensed text-xs ${
      isActive ? 'bg-[var(--cw-copper)]/20 text-[var(--cw-copper)] border border-[var(--cw-copper)]/50'
                : TONE_CLASSES.neutral
    }`
  }

  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        aria-pressed={activeCategory === 'all'}
        className={chipClass(activeCategory === 'all')}
        onClick={() => onSelect('all')}
      >
        All ({totalCount})
      </button>
      {CATEGORIES.map((category) => (
        <button
          key={category}
          type="button"
          aria-pressed={activeCategory === category}
          className={chipClass(activeCategory === category)}
          onClick={() => onSelect(category)}
        >
          {CATEGORY_LABELS[category]} ({counts[category]})
        </button>
      ))}
    </div>
  )
}

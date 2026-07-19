import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTacticalHighlightsReel } from '../hooks/useTacticalHighlightsReel'
import type { HighlightCategory } from '../hooks/useTacticalHighlightsReel'
import HighlightCategoryFilter from '../components/HighlightCategoryFilter'
import HighlightReel from '../components/HighlightReel'

const ALL_VIEW_CAP = 20

export default function TacticalHighlightsPage() {
  const { moments, counts, loading, error } = useTacticalHighlightsReel()
  const [activeCategory, setActiveCategory] = useState<'all' | HighlightCategory>('all')
  const [activeIndex, setActiveIndex] = useState(0)

  const filtered = useMemo(() => {
    if (!moments) return []
    if (activeCategory === 'all') {
      return [...moments].sort((a, b) => b.strength - a.strength).slice(0, ALL_VIEW_CAP)
    }
    return moments
      .filter((m) => m.category === activeCategory)
      .sort((a, b) => b.magnitude - a.magnitude)
  }, [moments, activeCategory])

  function selectCategory(category: 'all' | HighlightCategory) {
    setActiveCategory(category)
    setActiveIndex(0)
  }

  if (loading) return <p className="p-8 text-[var(--cw-muted)]">Loading…</p>
  if (error || !moments || !counts) {
    return (
      <p className="p-8 text-negative">
        Couldn&apos;t load your highlight reel. Confirm the Chesswright API server is running.
      </p>
    )
  }

  if (moments.length === 0) {
    return (
      <div className="min-h-full p-8">
        <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Tactical Highlights</h1>
        <p className="mt-4 text-sm text-[var(--cw-muted)]">
          Nothing to show yet — analyze more games to start building your highlight reel.
        </p>
        <Link
          to="/analysis-jobs"
          className="mt-3 inline-block rounded border border-[var(--cw-copper)] px-3 py-1.5 text-sm text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10"
        >
          Go to Analysis Jobs
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Tactical Highlights</h1>
      <p className="mt-1 text-sm text-[var(--cw-muted)]">
        A curated reel of moments most worth remembering.
      </p>
      <div className="mt-4">
        <HighlightCategoryFilter counts={counts} activeCategory={activeCategory} onSelect={selectCategory} />
      </div>
      <HighlightReel
        moments={filtered}
        activeCategory={activeCategory}
        activeIndex={activeIndex}
        onIndexChange={setActiveIndex}
      />
    </div>
  )
}

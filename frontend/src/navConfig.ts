// The Career/Explore/App grouping below only exists in dashboard/app.py's
// literal st.navigation({...}) dict -- it isn't in any data-layer
// structure PAGE_CANDIDATES could be enriched with without touching
// dashboard/data/search.py's shape. Hand-maintained; keep in sync if
// app.py's grouping changes.
import type { PageCandidate } from './lib/navCandidates'

export type NavGroup = 'Career' | 'Explore' | 'App'

export const NAV_GROUPS: NavGroup[] = ['Career', 'Explore', 'App']

export const PAGE_GROUP: Record<string, NavGroup> = {
  overview: 'Career',
  patterns: 'Career',
  openings: 'Career',
  matchups: 'Career',
  'game-endings': 'Career',
  'tactical-highlights': 'Career',
  insights: 'Career',
  points: 'Career',
  evolution: 'Career',
  'game-explorer': 'Explore',
  'drill-export': 'Explore',
  'training-queue': 'Explore',
  'srs-drills': 'Explore',
  'opening-tree': 'Explore',
  'opponent-prep': 'Explore',
  ask: 'Explore',
  settings: 'App',
  'analysis-jobs': 'App',
  'batch-impact': 'App',
}

export function groupPages(pages: PageCandidate[]): Record<NavGroup, PageCandidate[]> {
  const grouped: Record<NavGroup, PageCandidate[]> = { Career: [], Explore: [], App: [] }
  for (const page of pages) {
    const group = PAGE_GROUP[page.url_path]
    if (group) grouped[group].push(page)
  }
  return grouped
}

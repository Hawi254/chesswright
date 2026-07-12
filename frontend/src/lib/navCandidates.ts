// Bundled fallback for GET /api/nav/pages -- used only if that request
// fails (see hooks/usePageCandidates.ts). Hand-transcribed from
// dashboard/data/search.py's PAGE_CANDIDATES/SETTINGS_CANDIDATES; kept in
// sync manually, same accepted drift risk as navConfig.ts's group
// bucketing -- both are small, low-frequency-change duplication, not
// worth a build-time codegen step for.
export interface PageCandidate {
  category: 'page' | 'setting'
  title: string
  url_path: string
}

export const STATIC_CANDIDATES: PageCandidate[] = [
  { category: 'page', title: 'Overview', url_path: 'overview' },
  { category: 'page', title: 'Patterns & Tendencies', url_path: 'patterns' },
  { category: 'page', title: 'Openings & Repertoire', url_path: 'openings' },
  { category: 'page', title: 'Matchups & Opponents', url_path: 'matchups' },
  { category: 'page', title: 'Game Endings', url_path: 'game-endings' },
  { category: 'page', title: 'Tactical Highlights', url_path: 'tactical-highlights' },
  { category: 'page', title: 'Insights', url_path: 'insights' },
  { category: 'page', title: 'Where Your Points Go', url_path: 'points' },
  { category: 'page', title: 'Repertoire Evolution', url_path: 'evolution' },
  { category: 'page', title: 'Game Explorer', url_path: 'game-explorer' },
  { category: 'page', title: 'Drill Export', url_path: 'drill-export' },
  { category: 'page', title: 'Training Queue', url_path: 'training-queue' },
  { category: 'page', title: 'SRS Drills ✦', url_path: 'srs-drills' },
  { category: 'page', title: 'Opening Tree ✦', url_path: 'opening-tree' },
  { category: 'page', title: 'Opponent Prep', url_path: 'opponent-prep' },
  { category: 'page', title: 'Ask', url_path: 'ask' },
  { category: 'page', title: 'Settings', url_path: 'settings' },
  { category: 'page', title: 'Analysis Jobs', url_path: 'analysis-jobs' },
  { category: 'page', title: 'Batch Impact', url_path: 'batch-impact' },
  { category: 'setting', title: 'Anthropic API key', url_path: 'settings' },
  { category: 'setting', title: 'Live engine settings', url_path: 'settings' },
  { category: 'setting', title: 'Import an existing database', url_path: 'settings' },
  { category: 'setting', title: 'Chess.com account', url_path: 'settings' },
  { category: 'setting', title: 'Chesswright Pro', url_path: 'settings' },
  { category: 'setting', title: 'Support this project', url_path: 'settings' },
]

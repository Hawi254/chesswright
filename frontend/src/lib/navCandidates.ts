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
  anchor?: string
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
  { category: 'page', title: 'Training', url_path: 'training' },
  { category: 'page', title: 'Opening Tree ✦', url_path: 'opening-tree' },
  { category: 'page', title: 'Opponent Prep', url_path: 'opponent-prep' },
  { category: 'page', title: 'Ask', url_path: 'ask' },
  { category: 'page', title: 'Settings', url_path: 'settings' },
  { category: 'page', title: 'Analysis Jobs', url_path: 'analysis-jobs' },
  { category: 'page', title: 'Batch Impact', url_path: 'batch-impact' },
  { category: 'setting', title: 'Import an existing database', url_path: 'settings/account-data', anchor: 'db-import' },
  { category: 'setting', title: 'Chess.com account', url_path: 'settings/account-data', anchor: 'chesscom' },
  { category: 'setting', title: 'Engine location', url_path: 'settings/analysis-engine', anchor: 'engine-location' },
  { category: 'setting', title: 'Live engine settings', url_path: 'settings/analysis-engine', anchor: 'live-engine' },
  { category: 'setting', title: 'Engine profiles', url_path: 'settings/analysis-engine', anchor: 'engine-profiles' },
  { category: 'setting', title: 'Local timezone offset', url_path: 'settings/analytics-display', anchor: 'utc-offset' },
  { category: 'setting', title: 'Minimum sample size', url_path: 'settings/analytics-display', anchor: 'min-sample-size' },
  { category: 'setting', title: 'Non-standard variants', url_path: 'settings/ingestion', anchor: 'variant-policy' },
  { category: 'setting', title: 'Analysis queue order', url_path: 'settings/ingestion', anchor: 'queue-strategy' },
  { category: 'setting', title: 'Stored line length (plies)', url_path: 'settings/advanced', anchor: 'pv-max-len' },
  { category: 'setting', title: 'Reuse evaluations', url_path: 'settings/advanced', anchor: 'reuse-evals' },
  { category: 'setting', title: 'Consecutive failure limit', url_path: 'settings/advanced', anchor: 'consecutive-failure-limit' },
  { category: 'setting', title: 'Commit every N moves', url_path: 'settings/advanced', anchor: 'commit-every-n-moves' },
  { category: 'setting', title: 'Berserk clock fraction', url_path: 'settings/advanced', anchor: 'berserk-max-clock-fraction' },
  { category: 'setting', title: 'Backlog quota', url_path: 'settings/advanced', anchor: 'backlog-quota' },
  { category: 'setting', title: 'Backlog quota window', url_path: 'settings/advanced', anchor: 'backlog-quota-window' },
  { category: 'setting', title: 'Lichess sync request timeout', url_path: 'settings/advanced', anchor: 'sync-request-timeout' },
  { category: 'setting', title: 'Chess.com sync request timeout', url_path: 'settings/advanced', anchor: 'sync-chesscom-request-timeout' },
  { category: 'setting', title: 'Anthropic API key', url_path: 'settings/api-key', anchor: 'api-key' },
  { category: 'setting', title: 'Chesswright Pro', url_path: 'settings/pro', anchor: 'pro' },
  { category: 'setting', title: 'Support this project', url_path: 'settings/support', anchor: 'support' },
]

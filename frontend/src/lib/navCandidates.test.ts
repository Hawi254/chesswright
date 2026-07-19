import { describe, expect, it } from 'vitest'
import { STATIC_CANDIDATES } from './navCandidates'

describe('STATIC_CANDIDATES', () => {
  it('has 17 pages and 21 settings, matching the backend exactly', () => {
    expect(STATIC_CANDIDATES).toHaveLength(17 + 21)

    const pageUrlPaths = new Set(
      STATIC_CANDIDATES.filter((c) => c.category === 'page').map((c) => c.url_path),
    )
    expect(pageUrlPaths).toEqual(new Set([
      'overview', 'patterns', 'openings', 'matchups', 'game-endings',
      'tactical-highlights', 'insights', 'points', 'evolution',
      'game-explorer', 'training',
      'opening-tree', 'opponent-prep', 'ask', 'settings',
      'analysis-jobs', 'batch-impact',
    ]))

    const settingTitles = new Set(
      STATIC_CANDIDATES.filter((c) => c.category === 'setting').map((c) => c.title),
    )
    expect(settingTitles).toEqual(new Set([
      'Import an existing database', 'Chess.com account', 'Engine location',
      'Live engine settings', 'Engine profiles', 'Local timezone offset',
      'Minimum sample size', 'Non-standard variants', 'Analysis queue order',
      'Stored line length (plies)', 'Reuse evaluations', 'Consecutive failure limit',
      'Commit every N moves', 'Berserk clock fraction', 'Backlog quota',
      'Backlog quota window', 'Lichess sync request timeout',
      'Chess.com sync request timeout', 'Anthropic API key', 'Chesswright Pro',
      'Support this project',
    ]))

    const settingsWithAnchors = STATIC_CANDIDATES.filter((c) => c.category === 'setting')
    expect(settingsWithAnchors.every((c) => c.url_path.startsWith('settings/') && c.anchor)).toBe(true)
  })
})

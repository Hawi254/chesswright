import { describe, expect, it } from 'vitest'
import { STATIC_CANDIDATES } from './navCandidates'

describe('STATIC_CANDIDATES', () => {
  it('has 19 pages and 6 settings, matching the backend exactly', () => {
    expect(STATIC_CANDIDATES).toHaveLength(25)

    const pageUrlPaths = new Set(
      STATIC_CANDIDATES.filter((c) => c.category === 'page').map((c) => c.url_path),
    )
    expect(pageUrlPaths).toEqual(new Set([
      'overview', 'patterns', 'openings', 'matchups', 'game-endings',
      'tactical-highlights', 'insights', 'points', 'evolution',
      'game-explorer', 'drill-export', 'training-queue', 'srs-drills',
      'opening-tree', 'opponent-prep', 'ask', 'settings',
      'analysis-jobs', 'batch-impact',
    ]))

    const settingTitles = new Set(
      STATIC_CANDIDATES.filter((c) => c.category === 'setting').map((c) => c.title),
    )
    expect(settingTitles).toEqual(new Set([
      'Anthropic API key', 'Live engine settings', 'Import an existing database',
      'Chess.com account', 'Chesswright Pro', 'Support this project',
    ]))
  })
})

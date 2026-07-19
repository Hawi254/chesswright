import { describe, expect, it } from 'vitest'
import { groupPages, NAV_GROUPS, PAGE_GROUP } from './navConfig'
import { STATIC_CANDIDATES } from './lib/navCandidates'

describe('navConfig', () => {
  it('has exactly the 3 expected groups', () => {
    expect(NAV_GROUPS).toEqual(['Career', 'Explore', 'App'])
  })

  it('groups every static page into its correct group, matching dashboard/app.py', () => {
    const pages = STATIC_CANDIDATES.filter((c) => c.category === 'page')
    const grouped = groupPages(pages)

    expect(grouped.Career.map((p) => p.url_path)).toEqual([
      'overview', 'patterns', 'openings', 'matchups', 'game-endings',
      'tactical-highlights', 'insights', 'points', 'evolution',
    ])
    expect(grouped.Explore.map((p) => p.url_path)).toEqual([
      'game-explorer', 'training',
      'opening-tree', 'opponent-prep', 'ask',
    ])
    expect(grouped.App.map((p) => p.url_path)).toEqual([
      'settings', 'analysis-jobs', 'batch-impact',
    ])
  })

  it('assigns every page a group in PAGE_GROUP', () => {
    const pages = STATIC_CANDIDATES.filter((c) => c.category === 'page')
    for (const page of pages) {
      expect(PAGE_GROUP[page.url_path]).toBeDefined()
    }
  })
})

import { describe, expect, it } from 'vitest'
import { buildBreadcrumb } from './endingTree'
import type { EndingTree } from './endingTree'

const TREE: EndingTree = {
  ids: ['root', 'loss', 'loss/resignation', 'loss/resignation/hung_piece'],
  labels: ['All games', 'Loss', 'resignation', 'hung_piece'],
  parents: ['', 'root', 'loss', 'loss/resignation'],
  values: [100, 40, 20, 6],
}

describe('buildBreadcrumb', () => {
  it('returns the root state (no game list prompt) for a null path', () => {
    const result = buildBreadcrumb(TREE, null)
    expect(result).toEqual({ segments: ['All games'], count: 100, pctOfParent: null })
  })

  it('treats the literal "root" id the same as null', () => {
    const result = buildBreadcrumb(TREE, 'root')
    expect(result.segments).toEqual(['All games'])
  })

  it('builds a full breadcrumb with relabeled segments and % of parent', () => {
    const result = buildBreadcrumb(TREE, 'loss/resignation/hung_piece')
    expect(result.segments).toEqual(['Loss', 'Resignation', 'Hung a piece'])
    expect(result.count).toBe(6)
    expect(result.pctOfParent).toBe(30) // 6 / 20 * 100
  })

  it('returns pctOfParent null when the parent node is missing from the tree', () => {
    const oddTree: EndingTree = { ids: ['loss/checkmate'], labels: ['checkmate'], parents: ['loss'], values: [3] }
    const result = buildBreadcrumb(oddTree, 'loss/checkmate')
    expect(result.pctOfParent).toBeNull()
  })
})

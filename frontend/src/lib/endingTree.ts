import { END_TYPE_LABELS, RESIGNATION_REASON_LABELS } from './endingTreeLabels'

export interface EndingTree {
  ids: string[]
  labels: string[]
  parents: string[]
  values: number[]
}

export interface Breadcrumb {
  segments: string[]
  count: number
  pctOfParent: number | null
}

const RESULT_LABELS: Record<string, string> = { win: 'Win', draw: 'Draw', loss: 'Loss' }

function displayLabel(id: string, rawLabel: string): string {
  const segments = id.split('/')
  if (segments.length === 1) return RESULT_LABELS[segments[0]] ?? rawLabel
  const leaf = segments[segments.length - 1]
  return END_TYPE_LABELS[leaf] ?? RESIGNATION_REASON_LABELS[leaf] ?? rawLabel
}

export function buildBreadcrumb(tree: EndingTree, path: string | null): Breadcrumb {
  if (path === null || path === 'root') {
    const rootIndex = tree.ids.indexOf('root')
    return { segments: ['All games'], count: rootIndex >= 0 ? tree.values[rootIndex] : 0, pctOfParent: null }
  }

  const segments = path.split('/')
  const crumbLabels: string[] = []
  let count = 0
  let pctOfParent: number | null = null

  for (let depth = 1; depth <= segments.length; depth++) {
    const nodeId = segments.slice(0, depth).join('/')
    const nodeIndex = tree.ids.indexOf(nodeId)
    if (nodeIndex === -1) continue
    crumbLabels.push(displayLabel(nodeId, tree.labels[nodeIndex]))
    if (depth === segments.length) {
      count = tree.values[nodeIndex]
      const parentId = tree.parents[nodeIndex]
      const parentIndex = tree.ids.indexOf(parentId)
      const parentValue = parentIndex >= 0 ? tree.values[parentIndex] : null
      pctOfParent = parentValue ? (100.0 * count) / parentValue : null
    }
  }

  return { segments: crumbLabels, count, pctOfParent }
}

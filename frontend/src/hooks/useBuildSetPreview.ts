import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface BuildSetPosition {
  opening?: string
  move_number?: number
  phase?: string
  motif?: string
  cpl?: number
  wp_drop?: number
  hole_score?: number
  best_move_san?: string
}

export interface BuildSetSource {
  key: string
  label: string
  count: number
  positions: BuildSetPosition[]
}

export interface BuildSetPreview {
  sources: BuildSetSource[]
  total: number
}

export interface BuildSetParams {
  includeMotifs: boolean
  includeMoments: boolean
  includeHoles: boolean
  motifFilter: string | null
  topN: number
}

function toQuery(params: BuildSetParams): string {
  const q = new URLSearchParams({
    include_motifs: String(params.includeMotifs),
    include_moments: String(params.includeMoments),
    include_holes: String(params.includeHoles),
    top_n: String(params.topN),
  })
  if (params.motifFilter) q.set('motif_filter', params.motifFilter)
  return q.toString()
}

export function buildSetDownloadUrl(kind: 'pgn' | 'anki', params: BuildSetParams): string {
  return `${API_BASE}/api/training/build-set/download-${kind}?${toQuery(params)}`
}

export function useBuildSetPreview(params: BuildSetParams) {
  const [preview, setPreview] = useState<BuildSetPreview | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`${API_BASE}/api/training/build-set/preview?${toQuery(params)}`)
      .then((r) => r.json())
      .then((body: BuildSetPreview) => { if (!cancelled) { setPreview(body); setLoading(false) } })
      .catch(() => { if (!cancelled) { setPreview({ sources: [], total: 0 }); setLoading(false) } })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.includeMotifs, params.includeMoments, params.includeHoles, params.motifFilter, params.topN])

  return { preview, loading }
}

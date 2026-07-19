import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DRILL_PRESETS } from '../../lib/trainingPresets'
import { useBuildSetPreview, buildSetDownloadUrl, type BuildSetParams } from '../../hooks/useBuildSetPreview'
import AddToReviewButton from './AddToReviewButton'

const MOTIF_OPTIONS: Array<[string, string]> = [
  ['', 'All motifs'],
  ['fork', 'Fork'],
  ['pin', 'Pin'],
  ['skewer', 'Skewer'],
  ['discovered_attack', 'Discovered Attack'],
  ['back_rank_mate', 'Back-Rank Mate'],
  ['hanging', 'Hanging Piece'],
]

const TOP_N_MAX = 50

export default function BuildSetTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [includeMotifs, setIncludeMotifs] = useState(true)
  const [includeMoments, setIncludeMoments] = useState(true)
  const [includeHoles, setIncludeHoles] = useState(true)
  const [motifFilter, setMotifFilter] = useState('')
  const [topN, setTopN] = useState(20)

  useEffect(() => {
    const presetTitle = searchParams.get('preset')
    if (!presetTitle) return
    const preset = DRILL_PRESETS[presetTitle]
    if (preset) {
      setIncludeMotifs(preset.includeMotifs)
      setIncludeMoments(preset.includeMoments)
      setIncludeHoles(preset.includeHoles)
      setMotifFilter(preset.motifFilter ?? '')
    }
    const next = new URLSearchParams(searchParams)
    next.delete('preset')
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const params: BuildSetParams = {
    includeMotifs, includeMoments, includeHoles,
    motifFilter: includeMotifs ? (motifFilter || null) : null,
    topN,
  }
  const { preview, loading } = useBuildSetPreview(params)

  return (
    <div>
      <h2 className="font-condensed text-sm font-semibold text-[var(--cw-text)]">Sources</h2>
      <div className="mt-2 flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-xs text-[var(--cw-text)]">
          <input type="checkbox" checked={includeMotifs} onChange={(e) => setIncludeMotifs(e.target.checked)} />
          Missed tactics
        </label>
        <label className="flex items-center gap-2 text-xs text-[var(--cw-text)]">
          <input type="checkbox" checked={includeMoments} onChange={(e) => setIncludeMoments(e.target.checked)} />
          Decisive moments
        </label>
        <label className="flex items-center gap-2 text-xs text-[var(--cw-text)]">
          <input type="checkbox" checked={includeHoles} onChange={(e) => setIncludeHoles(e.target.checked)} />
          Repertoire holes
        </label>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <label htmlFor="training-top-n" className="text-xs text-[var(--cw-muted)]">Max positions per source</label>
        <input id="training-top-n" type="range" role="slider" min={5} max={TOP_N_MAX} step={5}
          value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
        <span className="text-xs text-[var(--cw-text)]">{topN}</span>
      </div>

      {includeMotifs && (
        <div className="mt-4">
          <label htmlFor="training-motif-filter" className="text-xs text-[var(--cw-muted)]">Motif filter</label>
          <select id="training-motif-filter" value={motifFilter} onChange={(e) => setMotifFilter(e.target.value)}
            className="ml-2 rounded border border-[var(--cw-line)] bg-[var(--cw-bg)] px-2 py-1 text-xs text-[var(--cw-text)]">
            {MOTIF_OPTIONS.map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
      )}

      <h2 className="mt-6 font-condensed text-sm font-semibold text-[var(--cw-text)]">
        Preview{preview ? ` — ${preview.total} position(s)` : ''}
      </h2>
      {loading && <p className="mt-2 text-xs text-[var(--cw-muted)]">Loading…</p>}
      {!loading && preview && preview.sources.length === 0 && (
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          No drill positions found yet. Run more Stockfish analysis and annotation first, then return here.
        </p>
      )}
      {!loading && preview?.sources.map((source) => (
        <div key={source.key} className="mt-3 rounded-md border border-[var(--cw-line)] p-3">
          <div className="font-condensed text-xs font-semibold text-[var(--cw-text)]">
            {source.label} ({source.count})
          </div>
        </div>
      ))}

      <h2 className="mt-6 font-condensed text-sm font-semibold text-[var(--cw-text)]">Export</h2>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <a href={buildSetDownloadUrl('pgn', params)}
           className="rounded border border-[var(--cw-copper)] px-3 py-1.5 text-xs text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10">
          Download Lichess Study PGN
        </a>
        <a href={buildSetDownloadUrl('anki', params)}
           className="rounded border border-[var(--cw-copper)] px-3 py-1.5 text-xs text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10">
          Download Anki CSV
        </a>
        <AddToReviewButton includeMotifs={includeMotifs} includeMoments={includeMoments}
          includeHoles={includeHoles} topN={topN} />
      </div>
      {includeMotifs && motifFilter && (
        <p className="mt-2 text-[10px] text-[var(--cw-muted)]">
          "Add to Review deck" adds every checked source's positions — the motif filter above only
          narrows the preview and downloads.
        </p>
      )}
    </div>
  )
}

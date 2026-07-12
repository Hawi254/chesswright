import { useOverviewData, type Finding } from '../hooks/useOverviewData'

// Same logic as dashboard/overview_view.py's _split_by_polarity + the
// tags = [...][:3] line in _render_identity_zone: top 2 strengths, top 2
// weakness-or-mixed findings, concatenated and capped at 3.
function topTraitTags(findings: Finding[]): Finding[] {
  const strengths = findings.filter((f) => f.polarity === 'strength').slice(0, 2)
  const weaknesses = findings
    .filter((f) => f.polarity === 'weakness' || f.polarity === 'mixed')
    .slice(0, 2)
  return [...strengths, ...weaknesses].slice(0, 3)
}

export default function OverviewPage() {
  const { stats, ratingSnapshot, streak, findings, narrative, loading, error } =
    useOverviewData()

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-text">Overview</h1>

      {loading && <p className="mt-4 text-text-muted">Loading…</p>}

      {!loading && error && (
        <p className="mt-4 text-negative">
          Couldn&apos;t load your Overview data. Confirm the Chesswright API server
          is running.
        </p>
      )}

      {!loading && !error && stats && ratingSnapshot && streak && findings && narrative !== null && (
        <div className="mt-4">
          <div className="flex gap-2">
            {topTraitTags(findings).map((f) => (
              <span
                key={f.title}
                className="rounded-full bg-bg-secondary px-3 py-1 text-sm text-accent-gold"
              >
                {f.title}
              </span>
            ))}
          </div>

          {ratingSnapshot.current_rating !== null && (
            <div className="mt-4">
              <span className="text-3xl font-semibold text-text">
                {ratingSnapshot.current_rating}
              </span>
              {ratingSnapshot.peak_rating !== null && (
                <span className="ml-2 text-sm text-text-muted">
                  {ratingSnapshot.current_rating < ratingSnapshot.peak_rating
                    ? `peak ${ratingSnapshot.peak_rating}`
                    : 'at peak'}
                </span>
              )}
              <div className="text-xs text-text-muted">
                Current rating
                {streak.length >= 2 ? ` · ${streak.length}-game ${streak.outcome} streak` : ''}
              </div>
            </div>
          )}

          <p className="mt-4 max-w-2xl text-text">{narrative}</p>

          <div className="mt-6 grid grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-text-muted">Total games</div>
              <div className="text-xl text-text">{stats.total_games.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Analyzed games</div>
              <div className="text-xl text-text">{stats.analyzed_games.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Win rate</div>
              <div className="text-xl text-text">
                {stats.win_pct !== null ? `${stats.win_pct.toFixed(1)}%` : '--'}
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">ACPL</div>
              <div className="text-xl text-text">
                {stats.acpl !== null ? stats.acpl.toFixed(1) : '--'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

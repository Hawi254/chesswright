import type { CSSProperties } from 'react'
import ZoneHead from './ZoneHead'
import type { Finding, HeadlineStats, RatingSnapshot, Streak } from '../hooks/useOverviewData'
import type { WinRateByColorRow } from '../hooks/useWinRateByColor'

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

function winPctFor(rows: WinRateByColorRow[] | null, color: 'white' | 'black'): number | null {
  const row = rows?.find((r) => r.player_color === color)
  return row ? row.win_pct : null
}

export default function IdentityZone({
  stats,
  ratingSnapshot,
  streak,
  findings,
  narrative,
  winRateByColor,
}: {
  stats: HeadlineStats
  ratingSnapshot: RatingSnapshot
  streak: Streak
  findings: Finding[]
  narrative: string
  winRateByColor: WinRateByColorRow[] | null
}) {
  const whiteWinPct = winPctFor(winRateByColor, 'white')
  const blackWinPct = winPctFor(winRateByColor, 'black')
  const railPct = stats.win_pct ?? 0

  return (
    <div data-testid="identity-zone" className="mt-6">
      <ZoneHead eyebrow="Who you are" title="Your chess identity" />

      <div
        className="relative mt-6 flex items-start gap-6 rounded-md p-2"
        style={{
          background:
            'radial-gradient(ellipse 60% 100% at 0% 30%, rgba(224,138,60,0.08), transparent 70%)',
        }}
      >
        {/* Win-rate rendered as a chess evaluation bar -- the one visual
            object every player already reads at a glance, repurposed here
            to show a career-long "who's winning" instead of a position's. */}
        <div className="flex-shrink-0 text-center">
          <div className="relative h-28 w-5 overflow-hidden rounded-sm border border-[var(--cw-line)] bg-[var(--cw-panel-2)]">
            <div className="absolute inset-x-0 top-1/2 z-10 h-px bg-[var(--cw-text)]/30" />
            <div
              className="cw-rail-fill absolute inset-x-0 bottom-0 w-full"
              style={
                {
                  '--cw-rail-target': `${railPct}%`,
                  background: 'linear-gradient(180deg, var(--cw-copper), #a95f22)',
                } as CSSProperties
              }
            />
            <div
              className="absolute inset-x-0 h-1.5 shadow-[0_0_8px_2px_rgba(224,138,60,0.65)]"
              style={{ bottom: `${railPct}%` }}
            />
          </div>
          <div className="mt-1.5 font-mono text-[10px] tabular-nums text-[var(--cw-muted)]">
            {stats.win_pct !== null ? `${railPct.toFixed(0)}%` : '--'}
          </div>
        </div>

        <div>
          <div className="flex gap-2">
            {topTraitTags(findings).map((f) => (
              <span
                key={f.title}
                className="rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] px-2.5 py-1 font-condensed text-[10px] font-semibold text-[var(--cw-text)]"
              >
                {f.title}
              </span>
            ))}
          </div>

          {ratingSnapshot.current_rating !== null && (
            <div className="mt-3">
              <span className="font-mono text-6xl font-semibold leading-none tracking-tight tabular-nums text-[var(--cw-text)]">
                {ratingSnapshot.current_rating}
              </span>
              {ratingSnapshot.peak_rating !== null && (
                <span className="ml-3 text-sm text-positive">
                  {ratingSnapshot.current_rating < ratingSnapshot.peak_rating
                    ? `peak ${ratingSnapshot.peak_rating}`
                    : 'at peak'}
                </span>
              )}
              <div className="mt-1 font-mono text-xs text-[var(--cw-muted)]">
                Current rating
                {streak.length >= 2 ? ` · ${streak.length}-game ${streak.outcome} streak` : ''}
              </div>
            </div>
          )}
        </div>
      </div>

      <p className="mt-5 max-w-[60ch] border-l-2 border-[var(--cw-line)] pl-3 font-cw-serif text-xs italic leading-relaxed text-[var(--cw-muted)]">
        {narrative}
      </p>

      <div className="mt-6 grid grid-cols-6 gap-5">
        <div>
          <div className="text-xs text-[var(--cw-muted)]">Total games</div>
          <div className="font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
            {stats.total_games.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--cw-muted)]">Analyzed</div>
          <div className="font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
            {stats.analyzed_games.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--cw-muted)]">Win rate</div>
          <div className="font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
            {stats.win_pct !== null ? `${stats.win_pct.toFixed(1)}%` : '--'}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--cw-muted)]">ACPL</div>
          <div className="font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
            {stats.acpl !== null ? stats.acpl.toFixed(1) : '--'}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--cw-muted)]">As White</div>
          <div className="font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
            {whiteWinPct !== null ? `${whiteWinPct.toFixed(1)}%` : '--'}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--cw-muted)]">As Black</div>
          <div className="font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
            {blackWinPct !== null ? `${blackWinPct.toFixed(1)}%` : '--'}
          </div>
        </div>
      </div>
    </div>
  )
}

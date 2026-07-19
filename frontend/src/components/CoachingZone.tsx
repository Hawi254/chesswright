import { Link } from 'react-router-dom'
import ZoneHead from './ZoneHead'
import type { Finding } from '../hooks/useOverviewData'

const SEVERITY_DOTS: Record<Finding['severity'], number> = { high: 3, medium: 2, low: 1 }

const FINDING_DEST: Record<string, { path: string; label: string }> = {
  'Piece blunder hot-spot': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Sharp positions and blunder rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Thinking time vs. blunder rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Clock pressure and blunder rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Castling and win rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'King moves off the back rank': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Toughest opponent': { path: '/matchups', label: 'Matchups & Opponents' },
  'Giant-killing and collapses': { path: '/matchups', label: 'Matchups & Opponents' },
  'Tactical highlights so far': { path: '/tactical-highlights', label: 'Tactical Highlights' },
  'How your games end': { path: '/game-endings', label: 'Game Endings' },
}

const QUICK_LINKS = [
  { path: '/insights', label: 'Insights' },
  { path: '/patterns', label: 'Patterns & Tendencies' },
  { path: '/openings', label: 'Openings & Repertoire' },
]

// Drives the ranked list / "top focus area" CTA. Deliberately UNCHANGED
// from before this task -- weakness-or-mixed, capped at 2 in list order
// before the ranked list's own severity sort/slice(3) ever applies (a
// preserved quirk, not a bug -- see CoachingZone.test.tsx).
function splitByPolarity(findings: Finding[]): { strengths: Finding[]; weaknesses: Finding[] } {
  return {
    strengths: findings.filter((f) => f.polarity === 'strength').slice(0, 2),
    weaknesses: findings
      .filter((f) => f.polarity === 'weakness' || f.polarity === 'mixed')
      .slice(0, 2),
  }
}

// New: independent 3-column preview grid. Each bucket is capped at 2
// separately -- NOT derived from splitByPolarity's weaknesses bucket
// above, so a 'mixed' finding can appear here even when it's excluded
// from the ranked list by the other function's own cap.
function splitByPolarityForPreview(findings: Finding[]): {
  strengths: Finding[]
  mixed: Finding[]
  focusAreas: Finding[]
} {
  return {
    strengths: findings.filter((f) => f.polarity === 'strength').slice(0, 2),
    mixed: findings.filter((f) => f.polarity === 'mixed').slice(0, 2),
    focusAreas: findings.filter((f) => f.polarity === 'weakness').slice(0, 2),
  }
}

export default function CoachingZone({
  findings,
  cached,
}: {
  findings: Finding[]
  cached: boolean | null
}) {
  const { weaknesses } = splitByPolarity(findings)
  const { strengths: previewStrengths, mixed, focusAreas } = splitByPolarityForPreview(findings)
  const ranked = [...weaknesses]
    .sort((a, b) => SEVERITY_DOTS[b.severity] - SEVERITY_DOTS[a.severity])
    .slice(0, 3)
  const topWeakness = ranked.length > 0 ? ranked[0].title : null
  const ctaLabel = cached ? 'View your coaching plan →' : 'Get your coaching plan →'

  return (
    <div className="mt-8 border-t border-[var(--cw-line)] pt-8">
      <ZoneHead eyebrow="What to work on" title="Your coaching plan" />

      {(previewStrengths.length > 0 || mixed.length > 0 || focusAreas.length > 0) && (
        <div data-testid="coaching-preview-grid" className="mt-5 grid grid-cols-3 gap-5">
          <div className="border-l-2 border-positive/40 pl-3">
            <div className="mb-1.5 font-condensed text-[10px] font-bold uppercase tracking-[0.12em] text-positive">
              Strengths
            </div>
            {previewStrengths.length === 0 && (
              <p className="mt-1 text-xs text-[var(--cw-muted)]">
                Nothing surfaced yet — check back after more games are analyzed.
              </p>
            )}
            {previewStrengths.map((f) => (
              <div key={f.title} className="mt-2 flex items-start gap-1.5">
                <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-positive" />
                <div>
                  <div className="font-condensed text-[11px] font-semibold text-[var(--cw-text)]">{f.title}</div>
                  <div className="text-xs text-[var(--cw-muted)]">{f.detail}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="border-l-2 border-[var(--cw-line)] pl-3">
            <div className="mb-1.5 font-condensed text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--cw-muted)]">
              Mixed
            </div>
            {mixed.length === 0 && (
              <p className="mt-1 text-xs text-[var(--cw-muted)]">Nothing mixed right now.</p>
            )}
            {mixed.map((f) => (
              <div key={f.title} className="mt-2 flex items-start gap-1.5">
                <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--cw-muted)]" />
                <div>
                  <div className="font-condensed text-[11px] font-semibold text-[var(--cw-text)]">{f.title}</div>
                  <div className="text-xs text-[var(--cw-muted)]">{f.detail}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="border-l-2 border-[var(--cw-copper)]/40 pl-3">
            <div className="mb-1.5 font-condensed text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--cw-copper)]">
              Focus areas
            </div>
            {focusAreas.length === 0 && (
              <p className="mt-1 text-xs text-[var(--cw-muted)]">
                Nothing surfaced yet — check back after more games are analyzed.
              </p>
            )}
            {focusAreas.map((f) => (
              <div key={f.title} className="mt-2 flex items-start gap-1.5">
                <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--cw-copper)]" />
                <div>
                  <div className="font-condensed text-[11px] font-semibold text-[var(--cw-text)]">{f.title}</div>
                  <div className="text-xs text-[var(--cw-muted)]">{f.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {ranked.length > 0 && (
        <div data-testid="coaching-ranked-list" className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-3">
          {ranked.map((f) => {
            const dots = SEVERITY_DOTS[f.severity]
            const dest = FINDING_DEST[f.title]
            return (
              <div key={f.title} className="flex items-center justify-between gap-4 py-1">
                <div>
                  <span className="mr-2 inline-flex gap-0.5 align-middle">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className={`h-1.5 w-1.5 rounded-full ${i < dots ? 'bg-[var(--cw-copper)]' : 'bg-[var(--cw-line)]'}`}
                      />
                    ))}
                  </span>
                  <span className="text-sm font-medium text-[var(--cw-text)]">{f.title}</span>
                  <div className="text-xs text-[var(--cw-muted)]">{f.detail}</div>
                </div>
                {dest && (
                  <Link
                    to={dest.path}
                    className="shrink-0 rounded border border-[var(--cw-line)] px-2 py-1 text-xs text-[var(--cw-text)] hover:bg-[var(--cw-line)]/40"
                  >
                    {dest.label}
                  </Link>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {topWeakness && (
          <span className="text-xs text-[var(--cw-muted)]">
            Because <strong className="text-[var(--cw-text)]">{topWeakness}</strong> is your top focus area —
          </span>
        )}
        <Link
          to="/insights"
          className="rounded border border-[var(--cw-copper)] px-3 py-1.5 text-sm text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10"
        >
          {ctaLabel}
        </Link>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {QUICK_LINKS.map((link) => (
          <Link
            key={link.path}
            to={link.path}
            className="rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] px-3 py-1.5 text-sm text-[var(--cw-text)] hover:bg-[var(--cw-line)]/40"
          >
            {link.label}
          </Link>
        ))}
      </div>
    </div>
  )
}

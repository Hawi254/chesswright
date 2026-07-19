import InsightCard from './InsightCard'
import type { Finding } from '../hooks/useOverviewData'

// Direct port of insights_view.py's _render_strengths_weaknesses filtering:
// mixed/neutral findings already bundle both directions or carry no
// direction at all, so they're excluded here (still visible in the full
// browse view above/below).
export default function StrengthsWeaknesses({ findings }: { findings: Finding[] }) {
  const strengths = findings.filter((f) => f.polarity === 'strength')
  const weaknesses = findings.filter((f) => f.polarity === 'weakness')

  if (strengths.length === 0 && weaknesses.length === 0) return null

  return (
    <div className="mt-4">
      <p className="text-xs text-[var(--cw-muted)]">
        Findings split by direction where the comparison has one — mixed or purely informational
        findings aren&apos;t shown here, see the full list above for those.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-4">
        <div data-testid="strengths-column">
          <h3 className="font-condensed text-xs font-bold uppercase tracking-[0.1em] text-positive">Strengths</h3>
          {strengths.length === 0 ? (
            <p className="mt-2 text-xs text-[var(--cw-muted)]">
              Nothing tagged as a clear strength yet with the data analyzed so far.
            </p>
          ) : (
            <div className="mt-2 flex flex-col gap-3">
              {strengths.map((f) => (
                <InsightCard key={f.title} finding={f} />
              ))}
            </div>
          )}
        </div>
        <div data-testid="weaknesses-column">
          <h3 className="font-condensed text-xs font-bold uppercase tracking-[0.1em] text-[var(--cw-copper)]">
            Areas to work on
          </h3>
          {weaknesses.length === 0 ? (
            <p className="mt-2 text-xs text-[var(--cw-muted)]">
              Nothing tagged as a clear weakness yet with the data analyzed so far.
            </p>
          ) : (
            <div className="mt-2 flex flex-col gap-3">
              {weaknesses.map((f) => (
                <InsightCard key={f.title} finding={f} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

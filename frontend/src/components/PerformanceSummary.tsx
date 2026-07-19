import type { ReactNode } from 'react'
import TrendArrow from './TrendArrow'
import type { HeadlineTrend } from '../hooks/useInsightsData'
import type { Finding, HeadlineStats } from '../hooks/useOverviewData'

function Tile({ label, value, right }: { label: string; value: string; right?: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-[var(--cw-muted)]">{label}</div>
      <div className="flex items-baseline font-mono text-sm font-semibold tabular-nums text-[var(--cw-text)]">
        {value}
        {right}
      </div>
    </div>
  )
}

export default function PerformanceSummary({
  stats,
  findings,
  trend,
}: {
  stats: HeadlineStats
  findings: Finding[]
  trend: HeadlineTrend | null
}) {
  const coveragePct = stats.total_games > 0 ? (100 * stats.analyzed_games) / stats.total_games : null
  const criticalCount = findings.filter((f) => f.severity === 'high').length
  const trainingOpportunityCount = findings.filter((f) => f.polarity === 'weakness').length

  const acplDisplay = stats.acpl !== null ? stats.acpl.toFixed(1) : '--'
  const blunderRateDisplay = stats.blunder_rate !== null ? `${stats.blunder_rate.toFixed(1)}%` : '--'
  const winPctDisplay = stats.win_pct !== null ? `${stats.win_pct.toFixed(1)}%` : '--'

  return (
    <div data-testid="performance-summary" className="mt-6">
      <div className="grid grid-cols-4 gap-5">
        <Tile label="Analyzed games" value={stats.analyzed_games.toLocaleString()} />
        <Tile label="Coverage" value={coveragePct !== null ? `${coveragePct.toFixed(0)}%` : '--'} />
        <Tile
          label="ACPL"
          value={acplDisplay}
          right={<TrendArrow delta={trend?.acpl_delta ?? null} goodDirection="down" />}
        />
        <Tile
          label="Blunder rate"
          value={blunderRateDisplay}
          right={<TrendArrow delta={trend?.blunder_rate_delta ?? null} goodDirection="down" unit="pp" />}
        />
        <Tile
          label="Win %"
          value={winPctDisplay}
          right={<TrendArrow delta={trend?.win_pct_delta ?? null} goodDirection="up" unit="pp" />}
        />
        <Tile label="Insights generated" value={String(findings.length)} />
        <Tile label="Critical findings" value={String(criticalCount)} />
        <Tile label="Training opportunities" value={String(trainingOpportunityCount)} />
      </div>
      {trend?.compared_to_date && (
        <p className="mt-2 text-[10px] text-[var(--cw-muted)]">Trend vs. {trend.compared_to_date}</p>
      )}
    </div>
  )
}

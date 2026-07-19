import type { AnalysisJobTelemetry } from '../hooks/useAnalysisJobStatus'

function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

export interface RunTelemetryProps {
  telemetry: AnalysisJobTelemetry | null
}

export default function RunTelemetry({ telemetry }: RunTelemetryProps) {
  if (!telemetry) return null

  const cacheHitLabel = !telemetry.reuseEvalsOn
    ? 'Off'
    : telemetry.cacheHitRate === null
      ? 'N/A'
      : `${Math.round(telemetry.cacheHitRate * 100)}%`

  const etaLabel = telemetry.eta === null ? 'calculating…' : formatDuration(telemetry.eta)

  return (
    <div className="grid grid-cols-3 gap-3" data-testid="run-telemetry">
      <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
        <p className="font-condensed text-[10px] uppercase tracking-[0.08em] text-[var(--cw-muted)]">Cache hit rate</p>
        <p className="mt-1 text-xl font-semibold text-[var(--cw-text)]">{cacheHitLabel}</p>
        {telemetry.reuseEvalsOn && telemetry.cacheHitRate !== null && (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--cw-line)]">
            <div
              className="h-full bg-[var(--cw-cyan)]"
              style={{ width: `${telemetry.cacheHitRate * 100}%` }}
            />
          </div>
        )}
      </div>
      <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
        <p className="font-condensed text-[10px] uppercase tracking-[0.08em] text-[var(--cw-muted)]">Est. time saved</p>
        <p className="mt-1 text-xl font-semibold text-[var(--cw-text)]">
          {telemetry.estTimeSavedSec === null ? '—' : formatDuration(telemetry.estTimeSavedSec)}
        </p>
      </div>
      <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)] p-4">
        <p className="font-condensed text-[10px] uppercase tracking-[0.08em] text-[var(--cw-muted)]">ETA</p>
        <p className="mt-1 text-xl font-semibold text-[var(--cw-text)]">{etaLabel}</p>
      </div>
    </div>
  )
}

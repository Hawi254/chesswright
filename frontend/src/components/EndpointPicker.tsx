import type { BatchImpactRun } from '../hooks/useBatchImpact'

// Pure reducer for the trend chart's 3-click selection state -- exported
// so BatchImpactPage can call it directly from the chart's onClick without
// EndpointPicker needing to render the chart itself. A 2-state toggle
// (pendingFirst is either null or a run id) rather than an explicit 3-way
// enum: resetting pendingFirst to null after the second click naturally
// makes a third click behave like a new first click.
export function applyChartClick(
  pendingFirst: number | null,
  clickedRunId: number,
  currentRunB: number,
): { runA: number | null; runB: number; pendingFirst: number | null } {
  if (pendingFirst === null) {
    return { runA: clickedRunId, runB: currentRunB, pendingFirst: clickedRunId }
  }
  const [runA, runB] = pendingFirst <= clickedRunId ? [pendingFirst, clickedRunId] : [clickedRunId, pendingFirst]
  return { runA, runB, pendingFirst: null }
}

export interface EndpointPickerProps {
  runs: BatchImpactRun[]
  range: { runA: number | null; runB: number | null }
  onChange: (runA: number | null, runB: number) => void
}

export default function EndpointPicker({ runs, range, onChange }: EndpointPickerProps) {
  const blocked = range.runA !== null && range.runA === range.runB

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-xs text-[var(--cw-muted)]">
        From
        <select
          aria-label="From"
          value={range.runA === null ? 'start' : String(range.runA)}
          onChange={(e) => onChange(e.target.value === 'start' ? null : Number(e.target.value), range.runB ?? 0)}
          className="mt-1 block rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] px-2 py-1 text-sm text-[var(--cw-text)]"
        >
          <option value="start">Start (no history)</option>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>
      </label>
      <label className="text-xs text-[var(--cw-muted)]">
        To
        <select
          aria-label="To"
          value={range.runB === null ? '' : String(range.runB)}
          onChange={(e) => onChange(range.runA, Number(e.target.value))}
          className="mt-1 block rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] px-2 py-1 text-sm text-[var(--cw-text)]"
        >
          {runs.map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>
      </label>
      {blocked && (
        <p className="text-xs text-negative">Pick two different batches to see a diff.</p>
      )}
    </div>
  )
}

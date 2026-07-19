import type { BatchImpactRecord } from '../hooks/useBatchImpact'

export default function RangeRecords({ records }: { records: BatchImpactRecord[] }) {
  if (records.length === 0) return null
  return (
    <div className="mt-4 rounded-md border border-[var(--cw-copper)]/40 bg-[var(--cw-copper)]/10 p-3">
      <h3 className="font-condensed text-sm font-bold text-[var(--cw-copper)]">Records set in this range</h3>
      <ul className="mt-1 space-y-1 text-xs text-[var(--cw-text)]">
        {records.map((r) => (
          <li key={`${r.runId}-${r.metric}`}>
            🏆 {r.label} set a personal-best {r.metric === 'acpl' ? 'ACPL' : 'blunder rate'} of {r.value.toFixed(1)}
            {r.priorBest !== null ? `, beating ${r.priorBest.toFixed(1)}` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

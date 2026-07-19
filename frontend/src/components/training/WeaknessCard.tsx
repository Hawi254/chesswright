import { useSearchParams } from 'react-router-dom'
import InsightCard from '../InsightCard'
import type { Finding } from '../../hooks/useOverviewData'
import { DRILL_PRESETS } from '../../lib/trainingPresets'

export default function WeaknessCard({ finding }: { finding: Finding }) {
  const [, setSearchParams] = useSearchParams()
  const hasPreset = finding.title in DRILL_PRESETS

  return (
    <div>
      <InsightCard finding={finding} />
      {hasPreset && (
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'build', preset: finding.title })}
          className="mt-2 rounded border border-[var(--cw-copper)] px-3 py-1.5 text-xs text-[var(--cw-copper)] hover:bg-[var(--cw-copper)]/10"
        >
          Build practice set from this weakness →
        </button>
      )}
    </div>
  )
}

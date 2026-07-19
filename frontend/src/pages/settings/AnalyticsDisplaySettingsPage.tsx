import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useSettingsResource } from '../../hooks/useSettingsResource'

interface AnalyticsSettings {
  utcOffsetHours: number
  minSampleSize: number
}

export default function AnalyticsDisplaySettingsPage() {
  const { value, loading, error, saving, saveError, save, resetting, reset } =
    useSettingsResource<AnalyticsSettings>('/api/settings/analytics', '/api/settings/analytics/reset')
  const [draft, setDraft] = useState<AnalyticsSettings | null>(null)

  if (loading) return <p className="text-sm text-[var(--cw-muted)]">Loading…</p>
  if (error || !value) {
    return <p className="text-sm text-negative">Couldn't load your Analytics & Display settings.</p>
  }

  const current = draft ?? value

  return (
    <div id="analytics-display" className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Analytics & Display</h1>

      <label id="utc-offset" htmlFor="utc-offset-input" className="mt-6 block text-sm text-[var(--cw-text)]">
        Local timezone offset (hours)
      </label>
      <input
        id="utc-offset-input"
        type="number"
        min={-12}
        max={14}
        value={current.utcOffsetHours}
        onChange={(e) => setDraft({ ...current, utcOffsetHours: Number(e.target.value) })}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="min-sample-size" htmlFor="min-sample-size-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Minimum sample size
      </label>
      <input
        id="min-sample-size-input"
        type="number"
        min={1}
        max={100}
        value={current.minSampleSize}
        onChange={(e) => setDraft({ ...current, minSampleSize: Number(e.target.value) })}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <div className="mt-6 flex gap-3">
        <Button size="sm" disabled={saving} onClick={() => save(current)}>
          {saving ? 'Working…' : 'Save'}
        </Button>
        <Button size="sm" variant="outline" disabled={resetting} onClick={() => reset()}>
          {resetting ? 'Working…' : 'Reset to defaults'}
        </Button>
      </div>
      {saveError && <p className="mt-2 text-xs text-negative">{saveError}</p>}
    </div>
  )
}

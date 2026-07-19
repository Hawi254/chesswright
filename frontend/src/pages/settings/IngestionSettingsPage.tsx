import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useSettingsResource } from '../../hooks/useSettingsResource'

interface IngestionSettings {
  variantPolicy: string
  queueStrategy: string
}

export default function IngestionSettingsPage() {
  const { value, loading, error, saving, saveError, save, resetting, reset } =
    useSettingsResource<IngestionSettings>('/api/settings/ingestion', '/api/settings/ingestion/reset')
  const [draft, setDraft] = useState<IngestionSettings | null>(null)

  if (loading) return <p className="text-sm text-[var(--cw-muted)]">Loading…</p>
  if (error || !value) {
    return <p className="text-sm text-negative">Couldn't load your Ingestion settings.</p>
  }

  const current = draft ?? value

  return (
    <div id="ingestion" className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Ingestion</h1>

      <label id="variant-policy" htmlFor="variant-policy-select" className="mt-6 block text-sm text-[var(--cw-text)]">
        Non-standard variants
      </label>
      <select
        id="variant-policy-select"
        value={current.variantPolicy}
        onChange={(e) => setDraft({ ...current, variantPolicy: e.target.value })}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      >
        <option value="skip">Skip</option>
        <option value="include">Include</option>
      </select>

      <label id="queue-strategy" htmlFor="queue-strategy-select" className="mt-4 block text-sm text-[var(--cw-text)]">
        Analysis queue order
      </label>
      <select
        id="queue-strategy-select"
        value={current.queueStrategy}
        onChange={(e) => setDraft({ ...current, queueStrategy: e.target.value })}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      >
        <option value="interleaved_by_year">Interleaved by year</option>
        <option value="chronological">Chronological</option>
        <option value="reverse_chronological">Reverse chronological</option>
      </select>

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

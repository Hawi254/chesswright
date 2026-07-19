import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useSettingsResource } from '../../hooks/useSettingsResource'

interface AdvancedSettings {
  pvMaxLen: number
  reuseEvals: boolean
  consecutiveFailureLimit: number
  commitEveryNMoves: number
  berserkMaxClockFraction: number
  backlogQuota: number
  backlogQuotaWindow: number
  syncRequestTimeoutSeconds: number
  syncChesscomRequestTimeoutSeconds: number
}

export default function AdvancedSettingsPage() {
  const { value, loading, error, saving, saveError, save } = useSettingsResource<AdvancedSettings>(
    '/api/settings/advanced',
  )
  const [draft, setDraft] = useState<AdvancedSettings | null>(null)

  if (loading) return <p className="text-sm text-[var(--cw-muted)]">Loading…</p>
  if (error || !value) {
    return <p className="text-sm text-negative">Couldn't load your Advanced settings.</p>
  }

  const current = draft ?? value
  const set = <K extends keyof AdvancedSettings>(key: K, val: AdvancedSettings[K]) =>
    setDraft({ ...current, [key]: val })

  return (
    <details id="advanced" className="max-w-md">
      <summary className="cursor-pointer font-condensed text-2xl text-[var(--cw-text)]">
        Advanced settings
      </summary>
      <p className="mt-2 text-xs text-[var(--cw-muted)]">
        Not commonly needed — these tune internal analysis/ingestion behavior.
      </p>

      <label id="pv-max-len" htmlFor="pv-max-len-input" className="mt-6 block text-sm text-[var(--cw-text)]">
        Stored line length (plies)
      </label>
      <input
        id="pv-max-len-input" type="number" min={1} max={60}
        value={current.pvMaxLen}
        onChange={(e) => set('pvMaxLen', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="reuse-evals" htmlFor="reuse-evals-input" className="mt-4 flex items-center gap-2 text-sm text-[var(--cw-text)]">
        <input
          id="reuse-evals-input" type="checkbox"
          checked={current.reuseEvals}
          onChange={(e) => set('reuseEvals', e.target.checked)}
        />
        Reuse a prior batch result for an exact-FEN repeat position
      </label>

      <label id="consecutive-failure-limit" htmlFor="consecutive-failure-limit-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Stop after N consecutive game failures
      </label>
      <input
        id="consecutive-failure-limit-input" type="number" min={1} max={100}
        value={current.consecutiveFailureLimit}
        onChange={(e) => set('consecutiveFailureLimit', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="commit-every-n-moves" htmlFor="commit-every-n-moves-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Commit every N moves
      </label>
      <input
        id="commit-every-n-moves-input" type="number" min={1} max={100}
        value={current.commitEveryNMoves}
        onChange={(e) => set('commitEveryNMoves', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="berserk-max-clock-fraction" htmlFor="berserk-max-clock-fraction-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Berserk clock fraction
      </label>
      <input
        id="berserk-max-clock-fraction-input" type="number" min={0} max={1} step={0.05}
        value={current.berserkMaxClockFraction}
        onChange={(e) => set('berserkMaxClockFraction', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="backlog-quota" htmlFor="backlog-quota-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Backlog quota
      </label>
      <input
        id="backlog-quota-input" type="number" min={0} max={1} step={0.05}
        value={current.backlogQuota}
        onChange={(e) => set('backlogQuota', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="backlog-quota-window" htmlFor="backlog-quota-window-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Backlog quota window (games)
      </label>
      <input
        id="backlog-quota-window-input" type="number" min={1} max={1000}
        value={current.backlogQuotaWindow}
        onChange={(e) => set('backlogQuotaWindow', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="sync-request-timeout" htmlFor="sync-request-timeout-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Lichess sync request timeout (s)
      </label>
      <input
        id="sync-request-timeout-input" type="number" min={1} max={300}
        value={current.syncRequestTimeoutSeconds}
        onChange={(e) => set('syncRequestTimeoutSeconds', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <label id="sync-chesscom-request-timeout" htmlFor="sync-chesscom-request-timeout-input" className="mt-4 block text-sm text-[var(--cw-text)]">
        Chess.com sync request timeout (s)
      </label>
      <input
        id="sync-chesscom-request-timeout-input" type="number" min={1} max={300}
        value={current.syncChesscomRequestTimeoutSeconds}
        onChange={(e) => set('syncChesscomRequestTimeoutSeconds', Number(e.target.value))}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />

      <div className="mt-6">
        <Button size="sm" disabled={saving} onClick={() => save(current)}>
          {saving ? 'Working…' : 'Save advanced settings'}
        </Button>
      </div>
      {saveError && <p className="mt-2 text-xs text-negative">{saveError}</p>}
    </details>
  )
}

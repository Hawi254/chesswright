import { useOpponentProfile } from '../hooks/useOpponentProfile'
import { useOpponentSwindleRate } from '../hooks/useOpponentSwindleRate'
import { useOpponentNarrative } from '../hooks/useOpponentNarrative'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'

interface ProfileColumn {
  key: string
  label: string
  format?: (value: unknown) => string
}

function pct(v: unknown): string {
  return typeof v === 'number' ? `${v.toFixed(1)}%` : '--'
}

function decimalOrDash(v: unknown): string {
  return v === null || v === undefined ? '--' : (v as number).toFixed(1)
}

function ProfileTable({
  rows, columns, caption,
}: {
  rows: Array<Record<string, unknown>>
  columns: ProfileColumn[]
  caption: string
}) {
  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">{caption}</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-xs text-[var(--cw-muted)]">No data yet.</p>
      ) : (
        <table className="mt-1 w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              {columns.map((c) => (
                <th key={c.key} scope="col" className="py-1 pr-2">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
                {columns.map((c) => (
                  <td key={c.key} className="py-1 pr-2 capitalize">
                    {c.format ? c.format(row[c.key]) : String(row[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function OpponentProfilePanel({ opponentName }: { opponentName: string }) {
  const { profile, loading, error } = useOpponentProfile(opponentName)
  const { swindle } = useOpponentSwindleRate(opponentName)
  const narrative = useOpponentNarrative(opponentName)
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()

  if (loading || error || !profile) return null

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <h3 className="font-condensed text-sm text-[var(--cw-text)]">Profile against {opponentName}</h3>
      <p className="mt-1 text-xs text-[var(--cw-muted)]">{profile.n_games} game(s) total.</p>

      <div className="mt-3 grid grid-cols-2 gap-4">
        <ProfileTable
          rows={profile.openings as unknown as Array<Record<string, unknown>>}
          caption="By opening"
          columns={[
            { key: 'opening_family', label: 'Opening' },
            { key: 'n_games', label: 'Games' },
            { key: 'win_pct', label: 'Win %', format: pct },
            { key: 'acpl', label: 'ACPL', format: decimalOrDash },
          ]}
        />
        <ProfileTable
          rows={profile.position as unknown as Array<Record<string, unknown>>}
          caption="By position character"
          columns={[
            { key: 'bucket', label: 'Position' },
            { key: 'n_games', label: 'Games' },
            { key: 'win_pct', label: 'Win %', format: pct },
          ]}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-4">
        <ProfileTable
          rows={profile.castling as unknown as Array<Record<string, unknown>>}
          caption="By castling configuration"
          columns={[
            { key: 'castling_config', label: 'Castling' },
            { key: 'n_games', label: 'Games' },
            { key: 'win_pct', label: 'Win %', format: pct },
          ]}
        />
        <ProfileTable
          rows={profile.action_side as unknown as Array<Record<string, unknown>>}
          caption="By attack side"
          columns={[
            { key: 'action_side', label: 'Side' },
            { key: 'n_games', label: 'Games' },
            { key: 'win_pct', label: 'Win %', format: pct },
          ]}
        />
      </div>
      <div className="mt-3">
        <ProfileTable
          rows={profile.clock as unknown as Array<Record<string, unknown>>}
          caption="By clock pressure"
          columns={[
            { key: 'bucket', label: 'Clock' },
            { key: 'n_moves', label: 'Moves' },
            { key: 'acpl', label: 'ACPL', format: decimalOrDash },
            { key: 'blunder_rate', label: 'Blunder %', format: pct },
          ]}
        />
      </div>

      {swindle && swindle.n_losses > 0 && swindle.swindle_rate_pct !== null && (
        <p className="mt-3 text-xs text-[var(--cw-muted)]">
          Missed swindle in {swindle.n_missed_swindle} of {swindle.n_losses} losses (
          {swindle.swindle_rate_pct.toFixed(0)}%).
        </p>
      )}

      {narrative.narrative && (
        <>
          {narrative.generatedAt && (
            <p className="mt-3 text-xs text-[var(--cw-muted)]">Generated {narrative.generatedAt}</p>
          )}
          <p className="mt-1 text-xs text-[var(--cw-text)]">{narrative.narrative}</p>
        </>
      )}
      {!claudeKeyAvailable && (
        <p className="mt-3 text-xs text-[var(--cw-muted)]">
          Add your own Anthropic API key on the Settings page to enable this.
        </p>
      )}
      <button
        type="button"
        disabled={!claudeKeyAvailable || narrative.generating}
        onClick={() => narrative.generate()}
        className="mt-3 rounded border border-[var(--cw-copper)] px-3 py-1.5 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
      >
        {narrative.narrative ? 'Regenerate commentary' : 'Generate commentary'}
      </button>
      {narrative.generateError && <p className="mt-2 text-negative">{narrative.generateError}</p>}
    </div>
  )
}

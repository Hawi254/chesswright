import { useProStatus } from '../hooks/useProStatus'
import { useTournamentPrepReport } from '../hooks/useTournamentPrepReport'
import { API_BASE } from '../lib/apiBase'

export interface TournamentPrepTabProps {
  username: string
}

function ProUpsell() {
  return (
    <p className="mt-2 text-xs text-[var(--cw-text)]">
      <strong>Tournament Prep Report</strong> is a Chesswright Pro feature — combine
      what this opponent tends to play with your own personal record against them in
      one downloadable document. Upgrade at{' '}
      <a href="https://chesswright.gumroad.com" target="_blank" rel="noreferrer" className="text-[var(--cw-copper)]">
        chesswright.gumroad.com
      </a>.
    </p>
  )
}

export default function TournamentPrepTab({ username }: TournamentPrepTabProps) {
  const proStatus = useProStatus()
  const { reportHtml, generatedAt, generate, generating, error, errorStatus } = useTournamentPrepReport(username)

  if (proStatus.loading) return null

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4" data-testid="tournament-prep-content">
      <p className="font-condensed text-xs uppercase text-[var(--cw-muted)]">Tournament Prep Report</p>
      <p className="mt-1 text-xs text-[var(--cw-muted)]">
        A downloadable prep sheet combining their repertoire with your personal record against them.
      </p>

      {errorStatus === 403 || !proStatus.active ? (
        <ProUpsell />
      ) : errorStatus === 501 ? (
        <p className="mt-2 text-xs text-negative">
          Pro is licensed but the chesswright_pro package couldn&apos;t be imported. Try reinstalling it.
        </p>
      ) : (
        <>
          <button
            type="button"
            disabled={generating}
            onClick={() => generate()}
            className="mt-2 rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
          >
            {reportHtml ? 'Regenerate report' : 'Generate Tournament Prep Report'}
          </button>

          {error && errorStatus !== 403 && errorStatus !== 501 && (
            <p className="mt-2 text-xs text-negative">{error}</p>
          )}

          {reportHtml && (
            <div className="mt-2 flex flex-col gap-1">
              <p className="text-[10px] text-[var(--cw-muted)]">Generated {generatedAt}</p>
              <a
                href={`${API_BASE}/api/opponent-prep/${encodeURIComponent(username)}/tournament-report/download.html`}
                download
                className="w-fit rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
              >
                Download report (HTML)
              </a>
            </div>
          )}
        </>
      )}
    </div>
  )
}

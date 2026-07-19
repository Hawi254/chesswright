import ReactMarkdown from 'react-markdown'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'
import { useGameReport } from '../hooks/useGameReport'
import { useProStatus } from '../hooks/useProStatus'
import { API_BASE } from '../lib/apiBase'

export interface GameReportPanelProps {
  gameId: string
  opponentName: string
  utcDate: string
}

function reportFilename(opponentName: string, utcDate: string, ext: 'md' | 'html'): string {
  const safeOpponent = (opponentName || 'game').replace(/ /g, '_')
  return `chesswright_report_${safeOpponent}_${utcDate}.${ext}`
}

function ProUpsell() {
  return (
    <p className="mt-2 text-xs text-[var(--cw-text)]">
      <strong>Game Report</strong> is a Chesswright Pro feature — a structured,
      phase-by-phase breakdown with annotated key moments and specific takeaways,
      exportable as Markdown. Upgrade at{' '}
      <a
        href="https://chesswright.gumroad.com"
        target="_blank"
        rel="noreferrer"
        className="text-[var(--cw-copper)]"
      >
        chesswright.gumroad.com
      </a>
      .
    </p>
  )
}

export default function GameReportPanel({ gameId, opponentName, utcDate }: GameReportPanelProps) {
  const proStatus = useProStatus()
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()
  const { reportText, generatedAt, generate, generating, error, errorStatus } = useGameReport(gameId)

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <p className="font-condensed text-xs uppercase text-[var(--cw-muted)]">Game Report</p>
      <p className="mt-1 text-xs text-[var(--cw-muted)]">
        A structured coach&apos;s review: phase-by-phase accuracy, every notable moment
        annotated, and concrete takeaways from this specific game.
      </p>

      {proStatus.loading ? null : errorStatus === 403 || !proStatus.active ? (
        <ProUpsell />
      ) : errorStatus === 501 ? (
        <p className="mt-2 text-xs text-negative">
          Pro is licensed but the chesswright_pro package couldn&apos;t be imported. Try reinstalling it.
        </p>
      ) : !claudeKeyAvailable ? (
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          Add your Anthropic API key on the Settings page to generate reports.
        </p>
      ) : (
        <>
          {reportText && (
            <>
              <p className="mt-2 text-[10px] text-[var(--cw-muted)]">Generated {generatedAt}</p>
              <div className="mt-2 text-xs text-[var(--cw-text)]">
                <ReactMarkdown>{reportText}</ReactMarkdown>
              </div>
            </>
          )}

          <button
            type="button"
            disabled={generating}
            onClick={() => generate()}
            className="mt-2 rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
          >
            {reportText ? 'Regenerate report' : 'Generate Game Report'}
          </button>

          {error && errorStatus !== 403 && errorStatus !== 501 && (
            <p className="mt-2 text-xs text-negative">{error}</p>
          )}

          {reportText && (
            <div className="mt-2 flex flex-col gap-1">
              <span className="flex gap-2">
                <a
                  href={`${API_BASE}/api/games/${gameId}/report/download.md`}
                  download
                  className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
                >
                  Download report (Markdown)
                </a>
                <a
                  href={`${API_BASE}/api/games/${gameId}/report/download.html`}
                  download
                  className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
                >
                  Download report (HTML)
                </a>
              </span>
              <p className="text-[10px] text-[var(--cw-muted)]">
                Saves to your Downloads folder as{' '}
                <code>{reportFilename(opponentName, utcDate, 'md')}</code> /{' '}
                <code>{reportFilename(opponentName, utcDate, 'html')}</code>
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

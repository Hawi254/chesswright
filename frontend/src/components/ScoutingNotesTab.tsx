import ReactMarkdown from 'react-markdown'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'
import { useOpponentPrepNotes } from '../hooks/useOpponentPrepNotes'

export interface ScoutingNotesTabProps {
  username: string
}

export default function ScoutingNotesTab({ username }: ScoutingNotesTabProps) {
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()
  const { narrative, generatedAt, generating, generateError, generate } = useOpponentPrepNotes(username)

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <p className="font-condensed text-xs uppercase text-[var(--cw-muted)]">Scouting Notes</p>

      {!claudeKeyAvailable ? (
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          Add your Anthropic API key on the Settings page to generate scouting notes.
        </p>
      ) : (
        <>
          {narrative && (
            <>
              <p className="mt-2 text-[10px] text-[var(--cw-muted)]">Generated {generatedAt}</p>
              <div className="mt-2 text-xs text-[var(--cw-text)]">
                <ReactMarkdown>{narrative}</ReactMarkdown>
              </div>
            </>
          )}
          <button
            type="button"
            disabled={generating}
            onClick={() => generate()}
            className="mt-2 rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
          >
            {narrative ? 'Regenerate notes' : 'Generate scouting notes'}
          </button>
          {generateError && <p className="mt-2 text-xs text-negative">{generateError}</p>}
        </>
      )}
    </div>
  )
}

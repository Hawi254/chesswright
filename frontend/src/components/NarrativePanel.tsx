import ReactMarkdown from 'react-markdown'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'
import type { UseNarrativeResult } from '../hooks/useInsightsNarratives'

export interface NarrativePanelProps {
  useNarrative: () => UseNarrativeResult
  description: string
  generateLabel: string
  regenerateLabel: string
}

// Shared by Synthesis and Coaching (decision 7) -- parameterized by which
// hook/labels it wraps rather than duplicating the gating logic twice.
export default function NarrativePanel({ useNarrative, description, generateLabel, regenerateLabel }: NarrativePanelProps) {
  const { narrative, generatedAt, generating, generateError, generate } = useNarrative()
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()

  return (
    <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
      <p className="text-xs text-[var(--cw-muted)]">{description}</p>

      {narrative && (
        <>
          {generatedAt && <p className="mt-3 text-[10px] text-[var(--cw-muted)]">Generated {generatedAt}</p>}
          <div className="mt-1 text-xs text-[var(--cw-text)]">
            <ReactMarkdown>{narrative}</ReactMarkdown>
          </div>
        </>
      )}

      {!claudeKeyAvailable && (
        <p className="mt-3 text-xs text-[var(--cw-muted)]">
          Add your own Anthropic API key on the Settings page to enable this.
        </p>
      )}

      <button
        type="button"
        disabled={!claudeKeyAvailable || generating}
        onClick={() => generate()}
        className="mt-3 rounded border border-[var(--cw-copper)] px-3 py-1.5 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
      >
        {narrative ? regenerateLabel : generateLabel}
      </button>

      {generateError && <p className="mt-2 text-xs text-negative">{generateError}</p>}
    </div>
  )
}

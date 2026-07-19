import { useEffect, useRef, useState } from 'react'
import type { Annotation } from '../hooks/useVariationAnnotation'

export interface AnnotationPanelProps {
  annotation: Annotation | null
  loading: boolean
  onSave: (glyph: string | null, comment: string | null) => void
  saveError: string | null
  onAskClaude: (userComment: string | null) => void
  aiLoading: boolean
  aiError: string | null
  claudeKeyAvailable: boolean
}

const GLYPHS = ['', '!', '!!', '?', '??', '!?', '?!']

export default function AnnotationPanel({
  annotation,
  loading,
  onSave,
  saveError,
  onAskClaude,
  aiLoading,
  aiError,
  claudeKeyAvailable,
}: AnnotationPanelProps) {
  const [glyph, setGlyph] = useState('')
  const [comment, setComment] = useState('')
  // Seeds local edit state from the fetched annotation exactly once per
  // mount, on the loading true -> false transition, not on every
  // annotation identity change -- askClaude()'s optimistic merge changes
  // `annotation` (and sometimes its id, on the very first AI comment)
  // without persisting glyph/comment, so re-seeding on every change would
  // silently wipe an unsaved, in-progress edit right after the user
  // clicks "Ask Claude". Gating on `!loading` alone (rather than the
  // transition) seeded too early: this component's mount effect commits
  // before the parent's own effect that kicks off the fetch, so on the
  // very first render `loading` is still its pristine initial `false`
  // and `annotation` is still `null` -- found live, seeding a real saved
  // annotation always rendered as an empty, unselected form.
  const seeded = useRef(false)
  const wasLoadingRef = useRef(loading)

  useEffect(() => {
    const wasLoading = wasLoadingRef.current
    wasLoadingRef.current = loading
    if (!loading && wasLoading && !seeded.current) {
      setGlyph(annotation?.glyph ?? '')
      setComment(annotation?.comment ?? '')
      seeded.current = true
    }
  }, [loading, annotation])

  const hasContent = Boolean(annotation?.glyph || annotation?.comment || annotation?.ai_comment)
  const aiLabel = annotation?.ai_comment ? 'Regenerate Claude comment' : 'Ask Claude to comment'

  return (
    <details
      className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4"
      open={hasContent}
    >
      <summary className="cursor-pointer font-condensed text-xs text-[var(--cw-text)]">
        Annotate this position
      </summary>

      <div className="mt-3 flex flex-wrap gap-1">
        {GLYPHS.map((g) => (
          <button
            key={g || 'none'}
            type="button"
            onClick={() => setGlyph(g)}
            className={`rounded border px-2 py-1 font-mono text-xs ${
              glyph === g
                ? 'border-[var(--cw-copper)] bg-[var(--cw-copper)]/20 text-[var(--cw-copper)]'
                : 'border-[var(--cw-copper)] text-[var(--cw-copper)]'
            }`}
          >
            {g || '(none)'}
          </button>
        ))}
      </div>

      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Your note on this position or move…"
        rows={3}
        className="mt-2 w-full rounded border border-[var(--cw-line)] bg-[var(--cw-panel)] p-2 font-condensed text-xs text-[var(--cw-text)]"
      />

      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          onClick={() => onSave(glyph || null, comment || null)}
          className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)]"
        >
          Save annotation
        </button>

        {claudeKeyAvailable ? (
          <button
            type="button"
            disabled={aiLoading}
            onClick={() => onAskClaude(comment || null)}
            className="rounded border border-[var(--cw-copper)] px-2 py-1 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
          >
            {aiLabel}
          </button>
        ) : (
          <span className="font-condensed text-xs text-[var(--cw-muted)]">
            Add API key in Settings to enable AI annotation.
          </span>
        )}
      </div>

      {saveError && <p className="mt-2 text-xs text-negative">{saveError}</p>}
      {aiError && <p className="mt-2 text-xs text-negative">{aiError}</p>}

      {annotation?.ai_comment && (
        <div className="mt-2">
          <p className="font-condensed text-xs text-[var(--cw-text)]">
            <em>Claude:</em> {annotation.ai_comment}
          </p>
          {annotation.generated_at && (
            <p className="mt-1 text-[10px] text-[var(--cw-muted)]">Generated {annotation.generated_at}</p>
          )}
        </div>
      )}
    </details>
  )
}

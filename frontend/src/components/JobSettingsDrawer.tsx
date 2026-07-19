import { useEffect, useState } from 'react'
import { Dialog as DialogPrimitive } from '@base-ui/react/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Accordion, AccordionItem } from './ui/accordion'
import { useAnalysisJobSettings } from '../hooks/useAnalysisJobSettings'
import type { AnalysisJobSettings } from '../hooks/useAnalysisJobSettings'

export interface JobSettingsDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  readOnly: boolean
}

export default function JobSettingsDrawer({ open, onOpenChange, readOnly }: JobSettingsDrawerProps) {
  const { settings, loading, error, saving, saveError, save } = useAnalysisJobSettings()
  const [draft, setDraft] = useState<AnalysisJobSettings | null>(null)

  useEffect(() => {
    if (settings) setDraft(settings)
  }, [settings])

  function field<K extends keyof AnalysisJobSettings>(key: K, value: AnalysisJobSettings[K]) {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/30" />
        <DialogPrimitive.Popup
          className="fixed top-0 right-0 z-50 h-full w-[360px] overflow-y-auto border-l border-[var(--cw-line)] bg-[var(--cw-panel)] p-6"
          data-testid="job-settings-drawer"
        >
          <DialogPrimitive.Title className="font-condensed text-lg text-[var(--cw-text)]">
            Engine and batch settings
          </DialogPrimitive.Title>

          {loading && <p className="mt-4 text-sm text-[var(--cw-muted)]">Loading…</p>}
          {error && <p className="mt-4 text-sm text-negative">Couldn&apos;t load settings.</p>}

          {draft && !loading && (
            <div className="mt-4 flex flex-col gap-4">
              {readOnly && (
                <p className="text-xs text-[var(--cw-copper)]">
                  Settings are read-only while a batch is running -- stop it first to change them.
                </p>
              )}

              <label className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
                Search depth
                <Input
                  type="number" min={1} max={40} disabled={readOnly}
                  value={draft.depth}
                  onChange={(e) => field('depth', Number(e.target.value))}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
                MultiPV (candidate lines per move)
                <Input
                  type="number" min={1} max={10} disabled={readOnly}
                  value={draft.multipv}
                  onChange={(e) => field('multipv', Number(e.target.value))}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
                Max games this run (0 = no limit)
                <Input
                  type="number" min={0} disabled={readOnly}
                  value={draft.maxGames ?? 0}
                  onChange={(e) => field('maxGames', Number(e.target.value) || null)}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
                Max duration this run (e.g. 2h, 90m -- blank = no limit)
                <Input
                  type="text" disabled={readOnly}
                  value={draft.maxDuration ?? ''}
                  onChange={(e) => field('maxDuration', e.target.value || null)}
                />
              </label>

              <Accordion>
                <AccordionItem value="advanced" title="Advanced">
                  <div className="flex flex-col gap-4">
                    <label className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
                      Engine threads
                      <Input
                        type="number" min={1} max={64} disabled={readOnly}
                        value={draft.threads}
                        onChange={(e) => field('threads', Number(e.target.value))}
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-xs text-[var(--cw-muted)]">
                      Engine hash table (MB)
                      <Input
                        type="number" min={16} max={8192} disabled={readOnly}
                        value={draft.hashMb}
                        onChange={(e) => field('hashMb', Number(e.target.value))}
                      />
                    </label>
                  </div>
                </AccordionItem>
              </Accordion>

              {saveError && <p className="text-xs text-negative">{saveError}</p>}

              {!readOnly && (
                <Button onClick={() => save(draft)} disabled={saving}>
                  {saving ? 'Saving…' : 'Save settings'}
                </Button>
              )}
            </div>
          )}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

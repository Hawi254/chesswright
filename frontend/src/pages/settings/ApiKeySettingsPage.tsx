import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useApiKeySettings } from '../../hooks/useApiKeySettings'

export default function ApiKeySettingsPage() {
  const { status, loading, error, saving, saveError, saveKey, removing, removeKey } = useApiKeySettings()
  const [keyDraft, setKeyDraft] = useState('')

  if (loading) return <p className="text-sm text-[var(--cw-muted)]">Loading…</p>
  if (error || !status) {
    return <p className="text-sm text-negative">Couldn't load your API key status.</p>
  }

  return (
    <div id="api-key" className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Anthropic API key</h1>
      <p className="mt-2 text-sm text-[var(--cw-text)]">
        {status.configured ? `Current key: ${status.masked}` : 'No API key configured.'}
      </p>
      {!status.secureBackend && (
        <p className="mt-2 text-xs text-negative">
          This computer has no OS credential store available, so the key is stored in a plain local file
          (less secure) at <code>~/.chesswright/api_key.txt</code> instead. If this is a shared computer,
          be aware other users could read it.
        </p>
      )}

      <label htmlFor="api-key-input" className="mt-6 block text-sm text-[var(--cw-text)]">Save a new key</label>
      <input
        id="api-key-input" type="password" placeholder="sk-ant-..."
        value={keyDraft}
        onChange={(e) => setKeyDraft(e.target.value)}
        className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
      />
      <div className="mt-4 flex gap-3">
        <Button size="sm" disabled={saving} onClick={() => saveKey(keyDraft)}>
          {saving ? 'Working…' : 'Save key'}
        </Button>
        <Button size="sm" variant="outline" disabled={removing || !status.configured} onClick={() => removeKey()}>
          {removing ? 'Working…' : 'Remove saved key'}
        </Button>
      </div>
      {saveError && <p className="mt-2 text-xs text-negative">{saveError}</p>}
    </div>
  )
}

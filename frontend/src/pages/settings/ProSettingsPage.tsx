import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useProLicense } from '../../hooks/useProLicense'

export default function ProSettingsPage() {
  const { license, active, activating, activateError, activateMessage, activate, deactivating, deactivate } =
    useProLicense()
  const [keyDraft, setKeyDraft] = useState('')

  return (
    <div id="pro" className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Chesswright Pro</h1>

      {!license?.available ? (
        <div className="mt-4">
          <p className="text-sm text-[var(--cw-text)]">
            Coach Mode and other Chesswright Pro features aren't installed on this computer.
          </p>
          <a
            href="https://gumroad.com"
            className="mt-2 inline-block text-sm text-[var(--cw-copper)] underline"
          >
            Get Chesswright Pro
          </a>
        </div>
      ) : active ? (
        <div className="mt-4">
          <p className="text-sm text-[var(--cw-text)]">License: {license.masked}</p>
          {license.purchaseEmail && (
            <p className="mt-1 text-xs text-[var(--cw-muted)]">Purchased by {license.purchaseEmail}</p>
          )}
          <Button size="sm" className="mt-3" variant="outline" disabled={deactivating} onClick={() => deactivate()}>
            {deactivating ? 'Working…' : 'Deactivate license'}
          </Button>
        </div>
      ) : (
        <div className="mt-4">
          <label htmlFor="pro-license-key-input" className="block text-sm text-[var(--cw-text)]">License key</label>
          <input
            id="pro-license-key-input" type="password"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
          />
          <Button size="sm" className="mt-2" disabled={activating} onClick={() => activate(keyDraft)}>
            {activating ? 'Working…' : 'Activate'}
          </Button>
          {activateMessage && <p className="mt-2 text-xs text-[var(--cw-text)]">{activateMessage}</p>}
          {activateError && <p className="mt-2 text-xs text-negative">{activateError}</p>}
        </div>
      )}
    </div>
  )
}

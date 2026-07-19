import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useDbImport } from '../../hooks/useDbImport'
import { useChesscomAccount } from '../../hooks/useChesscomAccount'

export default function AccountDataSettingsPage() {
  const { pending, importing, importError, startImport, confirming, confirmError, confirmImport, cancelImport } =
    useDbImport()
  const { username, pending: chesscomPending, pendingError, connect, disconnect, syncNow } = useChesscomAccount()

  const [pathDraft, setPathDraft] = useState('')
  const [usernameDraft, setUsernameDraft] = useState('')
  const [chesscomDraft, setChesscomDraft] = useState('')

  const usernameValue = pending ? (usernameDraft || pending.suggestedUsername) : ''

  return (
    <div id="account-data" className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Account & Data</h1>

      <section id="db-import" className="mt-6">
        <h2 className="font-condensed text-lg text-[var(--cw-text)]">Import an existing database</h2>
        {!pending ? (
          <>
            <label htmlFor="import-path-input" className="mt-2 block text-sm text-[var(--cw-text)]">
              Path to the database file on this computer
            </label>
            <input
              id="import-path-input" type="text"
              value={pathDraft}
              onChange={(e) => setPathDraft(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
            />
            <Button size="sm" className="mt-2" disabled={importing} onClick={() => startImport(pathDraft)}>
              {importing ? 'Working…' : 'Import'}
            </Button>
            {importError && <p className="mt-2 text-xs text-negative">{importError}</p>}
          </>
        ) : (
          <>
            <label htmlFor="import-username-input" className="mt-2 block text-sm text-[var(--cw-text)]">
              Lichess username for this database
            </label>
            <input
              id="import-username-input" type="text"
              value={usernameValue}
              onChange={(e) => setUsernameDraft(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
            />
            <div className="mt-2 flex gap-3">
              <Button
                size="sm" disabled={confirming || !usernameValue.trim()}
                onClick={() => confirmImport(usernameValue.trim())}
              >
                {confirming ? 'Working…' : 'Use this database'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => cancelImport()}>
                Cancel
              </Button>
            </div>
            {confirmError && <p className="mt-2 text-xs text-negative">{confirmError}</p>}
          </>
        )}
      </section>

      <section id="chesscom" className="mt-8">
        <h2 className="font-condensed text-lg text-[var(--cw-text)]">Chess.com account</h2>
        {username ? (
          <>
            <p className="mt-2 text-sm text-[var(--cw-text)]">Connected as {username}</p>
            <div className="mt-2 flex gap-3">
              <Button size="sm" disabled={chesscomPending} onClick={() => syncNow()}>
                {chesscomPending ? 'Working…' : 'Sync now'}
              </Button>
              <Button size="sm" variant="outline" disabled={chesscomPending} onClick={() => disconnect()}>
                Disconnect
              </Button>
            </div>
          </>
        ) : (
          <>
            <label htmlFor="chesscom-username-input" className="mt-2 block text-sm text-[var(--cw-text)]">
              Chess.com username
            </label>
            <input
              id="chesscom-username-input" type="text"
              value={chesscomDraft}
              onChange={(e) => setChesscomDraft(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
            />
            <Button size="sm" className="mt-2" disabled={chesscomPending} onClick={() => connect(chesscomDraft)}>
              Connect
            </Button>
          </>
        )}
        {pendingError && <p className="mt-2 text-xs text-negative">{pendingError}</p>}
      </section>
    </div>
  )
}

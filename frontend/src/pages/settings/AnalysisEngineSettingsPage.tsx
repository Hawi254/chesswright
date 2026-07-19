import { useState } from 'react'
import { Button } from '../../components/ui/button'
import { useEngineSettings, type LiveEngineSettings } from '../../hooks/useEngineSettings'
import { useEngineProfiles } from '../../hooks/useEngineProfiles'

export default function AnalysisEngineSettingsPage() {
  const {
    engine, loading, error,
    settingPath, pathError, setPath,
    redetecting, redetectError, redetect,
    savingLive, liveError, saveLive,
    resetting, reset, refetch,
  } = useEngineSettings()
  const {
    profiles, saving: savingProfile, saveProfile,
    applying, applyProfile,
    deleting, deleteProfile,
  } = useEngineProfiles()

  const [pathDraft, setPathDraft] = useState<string | null>(null)
  const [liveDraft, setLiveDraft] = useState<LiveEngineSettings | null>(null)
  const [newProfileName, setNewProfileName] = useState('')

  if (loading) return <p className="text-sm text-[var(--cw-muted)]">Loading…</p>
  if (error || !engine) {
    return <p className="text-sm text-negative">Couldn't load your Analysis Engine settings.</p>
  }

  const currentPath = pathDraft ?? engine.path ?? ''
  const currentLive = liveDraft ?? engine.live
  const setLive = <K extends keyof LiveEngineSettings>(key: K, val: LiveEngineSettings[K]) =>
    setLiveDraft({ ...currentLive, [key]: val })

  return (
    <div className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Analysis Engine</h1>

      <section id="engine-location" className="mt-6">
        <label htmlFor="engine-path-input" className="block text-sm text-[var(--cw-text)]">Engine path</label>
        <input
          id="engine-path-input" type="text"
          value={currentPath}
          onChange={(e) => setPathDraft(e.target.value)}
          className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
        />
        <div className="mt-2 flex gap-3">
          <Button size="sm" disabled={settingPath} onClick={() => setPath(currentPath)}>
            {settingPath ? 'Working…' : 'Set path'}
          </Button>
          <Button size="sm" variant="outline" disabled={redetecting} onClick={() => redetect()}>
            {redetecting ? 'Working…' : 'Re-detect'}
          </Button>
        </div>
        {pathError && <p className="mt-2 text-xs text-negative">{pathError}</p>}
        {redetectError && <p className="mt-2 text-xs text-negative">{redetectError}</p>}
      </section>

      <section id="live-engine" className="mt-8">
        <h2 className="font-condensed text-lg text-[var(--cw-text)]">Live engine settings</h2>

        <label htmlFor="live-time-sec-input" className="mt-4 block text-sm text-[var(--cw-text)]">Time limit (s)</label>
        <input
          id="live-time-sec-input" type="number" min={0.1} max={10} step={0.1}
          value={currentLive.timeSec}
          onChange={(e) => setLive('timeSec', Number(e.target.value))}
          className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
        />

        <label htmlFor="live-depth-input" className="mt-4 block text-sm text-[var(--cw-text)]">Depth limit</label>
        <input
          id="live-depth-input" type="number" min={5} max={40}
          value={currentLive.depth}
          onChange={(e) => setLive('depth', Number(e.target.value))}
          className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
        />

        <label htmlFor="live-threads-input" className="mt-4 block text-sm text-[var(--cw-text)]">Threads</label>
        <input
          id="live-threads-input" type="number" min={1} max={8}
          value={currentLive.threads}
          onChange={(e) => setLive('threads', Number(e.target.value))}
          className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
        />

        <label htmlFor="live-hash-mb-input" className="mt-4 block text-sm text-[var(--cw-text)]">Hash (MB)</label>
        <input
          id="live-hash-mb-input" type="number" min={16} max={1024} step={16}
          value={currentLive.hashMb}
          onChange={(e) => setLive('hashMb', Number(e.target.value))}
          className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
        />

        <label htmlFor="live-store-threshold-input" className="mt-4 block text-sm text-[var(--cw-text)]">
          Store threshold (depth)
        </label>
        <input
          id="live-store-threshold-input" type="number" min={0} max={50}
          value={currentLive.storeThreshold}
          onChange={(e) => setLive('storeThreshold', Number(e.target.value))}
          className="mt-1 w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
        />

        <label htmlFor="live-cloud-eval-input" className="mt-4 flex items-center gap-2 text-sm text-[var(--cw-text)]">
          <input
            id="live-cloud-eval-input" type="checkbox"
            checked={currentLive.useLichessCloudEval}
            onChange={(e) => setLive('useLichessCloudEval', e.target.checked)}
          />
          Use Lichess cloud evaluations
        </label>

        <div className="mt-4 flex gap-3">
          <Button size="sm" disabled={savingLive} onClick={() => saveLive(currentLive)}>
            {savingLive ? 'Working…' : 'Save and restart engine'}
          </Button>
          <Button size="sm" variant="outline" disabled={resetting} onClick={() => reset()}>
            {resetting ? 'Working…' : 'Reset to defaults'}
          </Button>
        </div>
        {liveError && <p className="mt-2 text-xs text-negative">{liveError}</p>}
      </section>

      <section id="engine-profiles" className="mt-8">
        <h2 className="font-condensed text-lg text-[var(--cw-text)]">Engine profiles</h2>
        <ul className="mt-2 space-y-2">
          {profiles.map((name) => (
            <li key={name} className="flex items-center gap-2 text-sm text-[var(--cw-text)]">
              {name}
              <Button
                size="sm" variant="outline" disabled={applying}
                onClick={async () => { await applyProfile(name); await refetch() }}
              >
                Apply
              </Button>
              <Button size="sm" variant="outline" disabled={deleting} onClick={() => deleteProfile(name)}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex gap-3">
          <input
            type="text" placeholder="Profile name"
            value={newProfileName}
            onChange={(e) => setNewProfileName(e.target.value)}
            className="w-full rounded border border-[var(--cw-line)] bg-transparent px-2 py-1 text-sm"
          />
          <Button
            size="sm" disabled={savingProfile || !newProfileName.trim()}
            onClick={() => { saveProfile(newProfileName.trim()); setNewProfileName('') }}
          >
            Save as profile
          </Button>
        </div>
      </section>
    </div>
  )
}

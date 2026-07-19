export default function SupportSettingsPage() {
  return (
    <div id="support" className="max-w-md">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Support this project</h1>
      <p className="mt-4 text-sm text-[var(--cw-text)]">
        The core app is free and stays free — this isn't a paywall. If you'd like to support ongoing
        development anyway:
      </p>
      <ul className="mt-3 space-y-2 text-sm">
        <li>
          <a href="https://github.com/sponsors/Hawi254" className="text-[var(--cw-copper)] underline">
            GitHub Sponsors
          </a>
        </li>
        <li>
          <a href="https://opencollective.com/chesswright" className="text-[var(--cw-copper)] underline">
            Open Collective
          </a>
        </li>
      </ul>
    </div>
  )
}

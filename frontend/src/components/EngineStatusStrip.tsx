import type { EngineStatusData } from '../hooks/useEngineStatus'

export default function EngineStatusStrip({
  status,
  totalGames,
  analyzedGames,
}: {
  status: EngineStatusData
  totalGames: number | null
  analyzedGames: number | null
}) {
  if (status.loading || status.error || totalGames === null || analyzedGames === null) return null

  const engineText = status.version ? `Stockfish ${status.version}` : 'Engine not detected'

  return (
    <div className="flex items-center gap-2 font-mono text-[11px] text-[var(--cw-muted)]">
      <span
        className={`h-1.5 w-1.5 rounded-full ${status.connected ? 'bg-[var(--cw-cyan)]' : 'bg-[var(--cw-line)]'}`}
      />
      <span>
        Chesswright v{status.appVersion} · {totalGames.toLocaleString()} games ·{' '}
        {analyzedGames.toLocaleString()} analyzed · {engineText}
      </span>
    </div>
  )
}

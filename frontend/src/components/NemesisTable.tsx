import ConfidenceBadge from './ConfidenceBadge'
import type { NemesisRow } from '../hooks/useNemesisOpponents'

export default function NemesisTable({
  rows, title, showExpectedSurprise = false, onSelect,
}: {
  rows: NemesisRow[]
  title: string
  showExpectedSurprise?: boolean
  onSelect: (opponentName: string) => void
}) {
  if (rows.length === 0) return null

  return (
    <div>
      <p className="text-xs text-[var(--cw-muted)]">{title}</p>
      <table className="mt-2 w-full border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
            <th scope="col" className="py-2 pr-3">Opponent</th>
            <th scope="col" className="py-2 pr-3">Games</th>
            <th scope="col" className="py-2 pr-3">W-D-L</th>
            <th scope="col" className="py-2 pr-3">Score %</th>
            {showExpectedSurprise && <th scope="col" className="py-2 pr-3">Expected %</th>}
            {showExpectedSurprise && <th scope="col" className="py-2">Surprise</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.opponent_name}
              onClick={() => onSelect(row.opponent_name)}
              className="cursor-pointer border-b border-[var(--cw-line)] text-[var(--cw-text)] hover:bg-[var(--cw-panel)]"
            >
              <td className="py-2 pr-3">{row.opponent_name}</td>
              <td className="py-2 pr-3">{row.n}</td>
              <td className="py-2 pr-3 font-mono">{row.wins}-{row.draws}-{row.losses}</td>
              <td className="py-2 pr-3">
                {row.score_pct.toFixed(1)}
                <ConfidenceBadge tier={row.confidence_tier} />
              </td>
              {showExpectedSurprise && <td className="py-2 pr-3">{row.expected_score_pct.toFixed(1)}</td>}
              {showExpectedSurprise && <td className="py-2">{row.surprise_pct.toFixed(1)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

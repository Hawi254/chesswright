import type { OpeningMove } from '../hooks/useOpeningTreeMoves'

export default function OpeningMoveTable({
  moves, playerTurn, onPlayMove,
}: {
  moves: OpeningMove[]
  playerTurn: boolean
  onPlayMove: (san: string) => void
}) {
  if (moves.length === 0) {
    return (
      <p className="p-3 text-xs text-[var(--cw-muted)]">
        {playerTurn
          ? 'No games recorded from this position — explore freely on the board.'
          : 'No opponent responses recorded here — play a move on the board to continue.'}
      </p>
    )
  }

  return (
    <div className="p-3">
      <p className="mb-2 text-xs text-[var(--cw-muted)]">
        {playerTurn ? 'Your moves from this position:' : 'Opponent responses seen here:'}
      </p>
      <table className="w-full text-xs text-[var(--cw-text)]">
        <thead>
          <tr className="text-left text-[var(--cw-muted)]">
            <th>Move</th>
            <th>Games</th>
            <th>Win%</th>
            <th>Draw%</th>
            <th>Loss%</th>
            {playerTurn && <th>Avg CPL</th>}
          </tr>
        </thead>
        <tbody>
          {moves.map((move) => (
            <tr key={move.san} onClick={() => onPlayMove(move.san)}
              className="cursor-pointer hover:bg-[var(--cw-panel-2)]">
              <td>{move.san}</td>
              <td>{move.n_games}</td>
              <td>{move.win_pct}</td>
              <td>{move.draw_pct}</td>
              <td>{move.loss_pct}</td>
              {playerTurn && <td>{move.avg_cpl ?? ''}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

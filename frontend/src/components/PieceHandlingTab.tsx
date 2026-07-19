import { useState } from 'react'
import Plot from 'react-plotly.js'
import { usePatternsPieces } from '../hooks/usePatternsPieces'
import { Accordion, AccordionItem } from './ui/accordion'
import { barChart, groupedBarChart, heatmap } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function PieceHandlingTab() {
  const [viewBy, setViewBy] = useState<'phase' | 'sharpness'>('phase')
  const { data, loading, error } = usePatternsPieces(viewBy)
  if (loading || error || !data) return null

  const groupCol = viewBy === 'phase' ? 'phase' : 'bucket'
  const heatmapCells = data.square_heatmap.cells.map((c) => ({
    ...c,
    n_moves_display: `${c.n_moves} moves`,
  }))
  const coveragePct = data.square_heatmap.n_total_in_scope
    ? (100 * data.square_heatmap.n_analyzed) / data.square_heatmap.n_total_in_scope
    : 0
  const noCastle = data.castling.acpl.find((r) => r.status === 'did not castle')

  return (
    <Accordion defaultOpen={['piece-movement']}>
      <AccordionItem value="piece-movement" title="Piece ACPL and blunder rate">
        <div className="grid grid-cols-2 gap-4">
          <Plot
            {...barChart(data.piece_movement, 'piece_name', 'acpl', THEME.negative, {
              xTitle: 'Piece moved', yTitle: 'ACPL (lower = more accurate)',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
          <Plot
            {...barChart(data.piece_movement, 'piece_name', 'blunder_rate', THEME.negative, {
              xTitle: 'Piece moved', yTitle: 'Blunder rate (% of moves)',
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </AccordionItem>

      <AccordionItem value="piece-by-view" title="Piece handling by game phase and position sharpness">
        <p className="mb-2 text-xs text-[var(--cw-muted)]">
          How each piece&apos;s blunder rate varies by game phase and position sharpness -- look
          for whether the piece patterns above hold in every context or shift depending on when
          in the game you&apos;re playing.
        </p>
        <div className="mb-3 flex gap-2">
          <button
            type="button"
            onClick={() => setViewBy('phase')}
            className={`rounded-md border px-3 py-1 font-condensed text-xs uppercase tracking-[0.08em] ${
              viewBy === 'phase'
                ? 'border-[var(--cw-copper)] text-[var(--cw-copper)]'
                : 'border-[var(--cw-line)] text-[var(--cw-muted)]'
            }`}
          >
            View phase
          </button>
          <button
            type="button"
            onClick={() => setViewBy('sharpness')}
            className={`rounded-md border px-3 py-1 font-condensed text-xs uppercase tracking-[0.08em] ${
              viewBy === 'sharpness'
                ? 'border-[var(--cw-copper)] text-[var(--cw-copper)]'
                : 'border-[var(--cw-line)] text-[var(--cw-muted)]'
            }`}
          >
            View sharpness
          </button>
        </div>
        <Plot
          {...groupedBarChart(data.piece_by_view, 'piece_name', groupCol, 'blunder_rate', {
            xTitle: 'Piece moved', yTitle: 'Blunder rate (% of moves)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="bishop-backrank" title="Bishop square color and rook/king back-rank handling">
        <p className="mb-2 text-xs text-[var(--cw-muted)]">
          Bishop blunder rate split by whether it moves to its own square colour (&quot;bad
          bishop&quot; positioning) vs. the opposite colour. Back-rank: rook and king blunder
          rates split by whether the piece is on the back rank or elsewhere.
        </p>
        <Plot
          {...barChart(data.bishop_square_color, 'square_color', 'blunder_rate', THEME.accentGold, {
            xTitle: 'Destination square color', yTitle: 'Blunder rate (% of moves)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
        <div className="mt-4">
          <Plot
            {...groupedBarChart(data.rook_king_backrank, 'piece_name', 'location', 'acpl', {
              xTitle: 'Piece', yTitle: 'ACPL (lower = more accurate)',
              colors: { 'back rank': THEME.positive, elsewhere: THEME.negative },
            })}
            config={{ displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </AccordionItem>

      <AccordionItem value="square-heatmap" title="Which squares see the most blunders?">
        <p className="mb-2 text-xs text-[var(--cw-muted)]">
          Blunder rate by the square your move landed on -- a finer-grained cut of the back-rank
          pattern above, across the full board. Hover a cell to see how many analyzed moves
          it&apos;s based on.
        </p>
        {data.square_heatmap.cells.length === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">
            Not enough data yet ({data.square_heatmap.n_analyzed} of{' '}
            {data.square_heatmap.n_total_in_scope} moves analyzed) -- it&apos;ll fill in as more
            games are analyzed.
          </p>
        ) : (
          <>
            <p className="mb-2 text-xs text-[var(--cw-muted)]">
              Based on {data.square_heatmap.n_analyzed} analyzed moves out of{' '}
              {data.square_heatmap.n_total_in_scope} total ({coveragePct.toFixed(1)}% analyzed)
              -- like every accuracy cut on this page, this is backlog-skewed toward
              recently-analyzed games, not a settled finding.
            </p>
            <Plot
              {...heatmap(heatmapCells, 'file', 'rank', 'blunder_rate', THEME.sequentialGold, {
                xTitle: 'File', yTitle: 'Rank', colorbarTitle: 'Blunder rate', valueSuffix: '%',
                hoverExtra: { column: 'n_moves_display', label: 'Sample size' },
              })}
              config={{ displayModeBar: false }}
              style={{ width: '100%' }}
            />
            {data.motif_backfill_needed && (
              <p className="mt-2 text-xs text-[var(--cw-muted)]">
                Missed-tactic classification (fork/pin/skewer/etc. by square) isn&apos;t shown
                here yet -- see Tactical Highlights&apos; motif backfill notice.
              </p>
            )}
          </>
        )}
      </AccordionItem>

      <AccordionItem value="castling" title="Castling and king safety">
        <p className="mb-2 text-xs text-[var(--cw-muted)]">
          Restricted to games lasting 30+ plies (the 95th percentile of the real castling-ply
          distribution), so short games that ended before castling was realistic aren&apos;t
          miscounted as &quot;chose not to castle.&quot;
        </p>
        <Plot
          {...barChart(data.castling.win, 'status', 'win_pct', THEME.positive, {
            xTitle: 'Castling', yTitle: 'Win rate (%)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
        <p className="mt-2 text-xs text-[var(--cw-muted)]">
          ACPL: {data.castling.acpl.map((r) => `${r.status}=${r.acpl.toFixed(1)} (${r.n_games} games)`).join(', ')}
          {' -- the "did not castle" side ('}
          {noCastle ? noCastle.n_games : 0}
          {' games) is a thin sample, treat as suggestive.'}
        </p>
      </AccordionItem>
    </Accordion>
  )
}

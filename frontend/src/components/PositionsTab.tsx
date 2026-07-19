import { useState } from 'react'
import Plot from 'react-plotly.js'
import { usePatternsPositions } from '../hooks/usePatternsPositions'
import { Accordion, AccordionItem } from './ui/accordion'
import { barChart } from '../lib/charts'
import { THEME } from '../lib/theme'

// Ported from patterns_view.py's _coverage_caption -- pure presentation
// logic (win/ACPL coverage disclosure), no chess-domain dependency, so
// it's a small local helper here rather than a server-side field. Shared
// by all 4 of this tab's comparison-style panels (4-7) rather than
// duplicated four times. Returns null when there's nothing analyzed yet
// for any category, matching _coverage_caption's own None return.
function coverageCaption(
  winRows: Array<{ n_games: number; [key: string]: unknown }>,
  acplRows: Array<{ n_games: number; [key: string]: unknown }>,
  keyField: string,
): string | null {
  if (acplRows.length === 0) return null
  const acplByKey = new Map(acplRows.map((r) => [String(r[keyField]), r.n_games]))
  let totalAnalyzed = 0
  let totalGames = 0
  const parts = winRows.map((w) => {
    const key = String(w[keyField])
    const nAnalyzed = acplByKey.get(key) ?? 0
    totalAnalyzed += nAnalyzed
    totalGames += w.n_games
    const pct = w.n_games ? (100 * nAnalyzed) / w.n_games : 0
    return `${key}: ${nAnalyzed} of ${w.n_games} (${pct.toFixed(1)}%)`
  })
  return (
    `ACPL/blunder-rate coverage is thin and backlog-skewed (only ${totalAnalyzed} of ` +
    `${totalGames} games total have any engine analysis) -- win rate above is full-coverage ` +
    'and honest from day one, but treat the accuracy numbers below as suggestive, not settled: ' +
    `${parts.join('; ')}.`
  )
}

const toggleClass = (active: boolean) =>
  `rounded-md border px-3 py-1 font-condensed text-xs uppercase tracking-[0.08em] ${
    active
      ? 'border-[var(--cw-copper)] text-[var(--cw-copper)]'
      : 'border-[var(--cw-line)] text-[var(--cw-muted)]'
  }`

export default function PositionsTab() {
  const [structureType, setStructureType] = useState<'endgame' | 'middlegame'>('endgame')
  const [grouped, setGrouped] = useState(false)
  const { data, loading, error } = usePatternsPositions(structureType, grouped)
  if (loading || error || !data) return null

  const { sharpness, material_structure, bishop_endings, position_character, game_side } = data

  return (
    <Accordion defaultOpen={['sharpness', 'material-structure']}>
      <AccordionItem value="sharpness" title="Blunder rate vs. position sharpness">
        <Plot
          {...barChart(sharpness, 'bucket', 'blunder_rate', THEME.negative, {
            xTitle: 'Position sharpness (engine best-move gap)', yTitle: 'Blunder rate (% of moves)',
          })}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </AccordionItem>

      <AccordionItem value="material-structure" title="Material structure win rate">
        <div className="mb-3 flex flex-wrap items-center gap-4">
          <div className="flex gap-2">
            <button type="button" onClick={() => setStructureType('endgame')}
              className={toggleClass(structureType === 'endgame')}>
              Endgame
            </button>
            <button type="button" onClick={() => setStructureType('middlegame')}
              className={toggleClass(structureType === 'middlegame')}>
              Middlegame
            </button>
          </div>
          <label className="flex items-center gap-2 text-xs text-[var(--cw-muted)]">
            <input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} />
            Group into broad categories
          </label>
        </div>
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--cw-line)] font-condensed text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
              <th scope="col" className="py-2 pr-3">{material_structure.label_header}</th>
              <th scope="col" className="py-2 pr-3">Games</th>
              <th scope="col" className="py-2 pr-3">Win %</th>
              <th scope="col" className="py-2 pr-3">Draw %</th>
              <th scope="col" className="py-2 pr-3">Loss %</th>
              <th scope="col" className="py-2 pr-3">ACPL</th>
              <th scope="col" className="py-2">Analyzed</th>
            </tr>
          </thead>
          <tbody>
            {material_structure.rows.map((row) => (
              <tr key={row.label} className="border-b border-[var(--cw-line)] text-[var(--cw-text)]">
                <td className="py-2 pr-3">{row.label}</td>
                <td className="py-2 pr-3">{row.n_games}</td>
                <td className="py-2 pr-3">{row.win_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{row.draw_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{row.loss_pct.toFixed(1)}</td>
                <td className="py-2 pr-3">{row.acpl === null ? '--' : row.acpl.toFixed(1)}</td>
                <td className="py-2">{row.n_analyzed}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {material_structure.n_unanalyzed > 0 && (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">
            ACPL is blank for {material_structure.n_unanalyzed} of {material_structure.rows.length}{' '}
            structures -- no analyzed games have reached them yet, not a data error.
          </p>
        )}
      </AccordionItem>

      <AccordionItem value="bishop-endings" title="Same-color vs. opposite-color bishop endings">
        {bishop_endings.length < 2 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              {(['opposite', 'same'] as const).map((bucket) => {
                const row = bishop_endings.find((r) => r.bucket === bucket)
                if (!row) return null
                return (
                  <div key={bucket} className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
                    <p className="font-condensed text-[11px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
                      {bucket === 'opposite' ? 'Opposite-color bishop endings ACPL' : 'Same-color bishop endings ACPL'}
                    </p>
                    <p className="mt-1 text-xl text-[var(--cw-text)]">{row.acpl.toFixed(1)}</p>
                    <p className="mt-1 text-xs text-[var(--cw-muted)]">{row.n_moves} moves</p>
                  </div>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-[var(--cw-muted)]">
              Win/draw rate showed no meaningful difference between same- and opposite-color bishop
              endings in this data -- ACPL, not outcome, is the real signal here.
            </p>
          </>
        )}
      </AccordionItem>

      <AccordionItem value="open-semi-closed" title="Open, semi-open, or closed?">
        {position_character.n_classified === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Plot
                {...barChart(position_character.bucket_win, 'bucket', 'win_pct', THEME.positive, {
                  height: 240, xTitle: 'Position type', yTitle: 'Win rate (%)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
              <Plot
                {...barChart(position_character.bucket_acpl, 'bucket', 'acpl', THEME.negative, {
                  height: 240, xTitle: 'Position type', yTitle: 'ACPL (lower = more accurate)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
            {(() => {
              const caption = coverageCaption(position_character.bucket_win, position_character.bucket_acpl, 'bucket')
              return caption ? <p className="mt-2 text-xs text-[var(--cw-muted)]">{caption}</p> : null
            })()}
            {position_character.central_tension_pct !== null && (
              <p className="mt-2 text-xs text-[var(--cw-muted)]">
                Within semi-open games, {position_character.central_tension_pct.toFixed(1)}% still had
                unresolved central pawn tension (adjacent pawns that could still capture each other) at
                the checkpoint.
              </p>
            )}
          </>
        )}
      </AccordionItem>

      <AccordionItem value="symmetric-asymmetric" title="Symmetric vs. asymmetric pawn structure">
        {position_character.n_classified === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Plot
                {...barChart(position_character.symmetric_win, 'symmetry_label', 'win_pct', THEME.positive, {
                  height: 240, xTitle: 'Pawn structure', yTitle: 'Win rate (%)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
              <Plot
                {...barChart(position_character.symmetric_acpl, 'symmetry_label', 'acpl', THEME.negative, {
                  height: 240, xTitle: 'Pawn structure', yTitle: 'ACPL (lower = more accurate)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
            {(() => {
              const caption = coverageCaption(
                position_character.symmetric_win, position_character.symmetric_acpl, 'symmetry_label')
              return caption ? <p className="mt-2 text-xs text-[var(--cw-muted)]">{caption}</p> : null
            })()}
          </>
        )}
      </AccordionItem>

      <AccordionItem value="castling" title="Castling configuration">
        {game_side.castling_win.length === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Plot
                {...barChart(game_side.castling_win, 'castling_config', 'win_pct', THEME.positive, {
                  height: 240, xTitle: 'Castling configuration', yTitle: 'Win rate (%)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
              <Plot
                {...barChart(game_side.castling_acpl, 'castling_config', 'acpl', THEME.negative, {
                  height: 240, xTitle: 'Castling configuration', yTitle: 'ACPL (lower = more accurate)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
            {(() => {
              const caption = coverageCaption(game_side.castling_win, game_side.castling_acpl, 'castling_config')
              return caption ? <p className="mt-2 text-xs text-[var(--cw-muted)]">{caption}</p> : null
            })()}
          </>
        )}
      </AccordionItem>

      <AccordionItem value="queenside-kingside" title="Where did the fight happen: queenside or kingside?">
        {game_side.action_win.length === 0 ? (
          <p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Plot
                {...barChart(game_side.action_win, 'action_side', 'win_pct', THEME.positive, {
                  height: 240, xTitle: 'Where the fight happened', yTitle: 'Win rate (%)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
              <Plot
                {...barChart(game_side.action_acpl, 'action_side', 'acpl', THEME.negative, {
                  height: 240, xTitle: 'Where the fight happened', yTitle: 'ACPL (lower = more accurate)',
                })}
                config={{ displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
            {(() => {
              const caption = coverageCaption(game_side.action_win, game_side.action_acpl, 'action_side')
              return caption ? <p className="mt-2 text-xs text-[var(--cw-muted)]">{caption}</p> : null
            })()}
          </>
        )}
      </AccordionItem>
    </Accordion>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Chess } from 'chess.js'
import Chessboard from '../components/Chessboard'
import MoveList from '../components/MoveList'
import EvalGraph from '../components/EvalGraph'
import { activeChipsFor, TONE_CLASSES } from '../lib/badges'
import { useGameDetail } from '../hooks/useGameDetail'
import { useAnalysePosition } from '../hooks/useAnalysePosition'
import { useVariation } from '../hooks/useVariation'
import VariationPanel from '../components/VariationPanel'
import { useSavedVariations } from '../hooks/useSavedVariations'
import SavedVariationsPanel from '../components/SavedVariationsPanel'
import { useClaudeKeyStatus } from '../hooks/useClaudeKeyStatus'
import { useGameAnnotation } from '../hooks/useGameAnnotation'
import { useVariationAnnotation } from '../hooks/useVariationAnnotation'
import AnnotationPanel from '../components/AnnotationPanel'
import GameReportPanel from '../components/GameReportPanel'
import { useBoardChat } from '../hooks/useBoardChat'
import BoardChatPanel from '../components/BoardChatPanel'
import { API_BASE } from '../lib/apiBase'

export default function GameDetailPage() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const { header, moves, winProb, loading, error, notFound } = useGameDetail(gameId ?? null)
  const [ply, setPly] = useState<number | null>(null)
  const { analyse, result: analysis, resultFen, status: analysisStatus, loading: analysing } = useAnalysePosition()
  const savedVariations = useSavedVariations(gameId ?? null)
  const variation = useVariation(gameId ?? '', savedVariations.refetch)
  const { available: claudeKeyAvailable } = useClaudeKeyStatus()
  const boardChat = useBoardChat(gameId ?? '')

  const currentMove = useMemo(() => moves?.find((m) => m.ply === ply) ?? null, [moves, ply])
  const mainlineFen = currentMove?.fen_after ?? moves?.[0]?.fen_before

  const gameAnnotation = useGameAnnotation(gameId ?? '', ply, mainlineFen ?? null)
  const variationAnnotation = useVariationAnnotation(
    variation.variationId, variation.step, variation.currentFen,
  )

  useEffect(() => {
    if (moves && moves.length > 0) {
      setPly(moves[moves.length - 1].ply)
    }
  }, [moves])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (variation.active) {
        if (e.key === 'ArrowLeft') {
          e.preventDefault()
          variation.stepTo(variation.step - 1)
        } else if (e.key === 'ArrowRight') {
          e.preventDefault()
          variation.stepTo(variation.step + 1)
        }
        return
      }
      if (!moves || moves.length === 0 || ply === null) return
      const idx = moves.findIndex((m) => m.ply === ply)
      if (e.key === 'ArrowLeft' && idx > 0) {
        e.preventDefault()
        setPly(moves[idx - 1].ply)
      } else if (e.key === 'ArrowRight' && idx >= 0 && idx < moves.length - 1) {
        e.preventDefault()
        setPly(moves[idx + 1].ply)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [moves, ply, variation.active, variation.step, variation.stepTo])

  const boardFen = variation.active ? (variation.currentFen ?? undefined) : mainlineFen

  const lastMoveSquares = useMemo(() => {
    if (!currentMove) return { from: null, to: null }
    try {
      const chessGame = new Chess(currentMove.fen_before)
      const move = chessGame.move(currentMove.san)
      return move ? { from: move.from, to: move.to } : { from: null, to: null }
    } catch {
      return { from: null, to: null }
    }
  }, [currentMove])

  const displayLastMoveSquares = variation.active
    ? (variation.lastMoveSquares ?? { from: null, to: null })
    : lastMoveSquares

  function selectMainlinePly(newPly: number) {
    variation.exit()
    setPly(newPly)
  }

  async function handleDeleteVariation(variationId: string) {
    await fetch(`${API_BASE}/api/variations/${variationId}`, { method: 'DELETE' }).catch(() => {})
    savedVariations.refetch()
    if (variation.variationId === variationId) {
      variation.exit()
    }
  }

  const engineArrows = useMemo(() => {
    if (analysisStatus !== 'ok' || !analysis?.best_move_from || !analysis?.best_move_to) return []
    return [{ from: analysis.best_move_from, to: analysis.best_move_to, color: 'var(--color-positive)' }]
  }, [analysis, analysisStatus])

  function evalContextFor(targetFen: string | null | undefined) {
    if (!targetFen || analysisStatus !== 'ok' || !analysis || resultFen !== targetFen) {
      return { evalCp: null, bestMoveSan: null }
    }
    return { evalCp: analysis.eval_cp, bestMoveSan: analysis.best_move_san }
  }

  if (loading) return <p className="p-8 text-[var(--cw-muted)]">Loading…</p>
  if (notFound) return <p className="p-8 text-negative">This game couldn&apos;t be found.</p>
  if (error || !header || !moves) {
    return (
      <p className="p-8 text-negative">
        Couldn&apos;t load this game. Confirm the Chesswright API server is running.
      </p>
    )
  }

  const chips = activeChipsFor(header)

  return (
    <div className="min-h-full p-8">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="font-condensed text-xs text-[var(--cw-copper)]"
      >
        ← Back to Game Explorer
      </button>

      <p className="mt-2 font-condensed text-lg text-[var(--cw-text)]">
        vs. {header.opponent_name} · {header.utc_date} ·{' '}
        <span className="capitalize">{header.outcome_for_player}</span> · {header.opening_family}
        {header.lichess_url && (
          <a
            href={header.lichess_url}
            target="_blank"
            rel="noreferrer"
            className="ml-2 text-[var(--cw-copper)]"
          >
            View ↗
          </a>
        )}
      </p>
      {chips.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {chips.map((chip) => (
            <span
              key={chip.key}
              className={`rounded px-1.5 py-0.5 font-condensed text-[9px] ${TONE_CLASSES[chip.tone]}`}
            >
              {chip.label}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 grid grid-cols-[minmax(280px,440px)_1fr] gap-4">
        <Chessboard
          fen={boardFen}
          orientation={header.player_color === 'black' ? 'black' : 'white'}
          lastmoveFrom={displayLastMoveSquares.from}
          lastmoveTo={displayLastMoveSquares.to}
          arrows={[...engineArrows, ...boardChat.arrows]}
          highlightedSquares={boardChat.highlights}
          interactive
          onMove={(move) => {
            if (ply !== null) variation.applyMove(ply, mainlineFen!, move)
          }}
        />
        <MoveList moves={moves} currentPly={ply} onSelectPly={selectMainlinePly} />
      </div>

      <VariationPanel
        active={variation.active}
        branchPly={variation.branchPly}
        sans={variation.sans}
        step={variation.step}
        onStepTo={variation.stepTo}
        onExit={variation.exit}
        onDiscard={variation.discard}
      />

      {variation.active && variation.variationId && (
        <AnnotationPanel
          key={`var-${variation.variationId}-${variation.step}`}
          annotation={variationAnnotation.annotation}
          loading={variationAnnotation.loading}
          onSave={variationAnnotation.save}
          saveError={variationAnnotation.saveError}
          onAskClaude={(userComment) => {
            const { evalCp, bestMoveSan } = evalContextFor(variation.currentFen)
            variationAnnotation.askClaude(evalCp, bestMoveSan, userComment)
          }}
          aiLoading={variationAnnotation.aiLoading}
          aiError={variationAnnotation.aiError}
          claudeKeyAvailable={claudeKeyAvailable}
        />
      )}

      <SavedVariationsPanel
        variations={savedVariations.variations}
        onLoad={variation.load}
        onDelete={handleDeleteVariation}
      />

      <div className="mt-4">
        <EvalGraph winProb={winProb ?? []} currentPly={ply} onSelectPly={selectMainlinePly} />
      </div>

      {ply !== null && (
        <AnnotationPanel
          key={`game-${gameId}-${ply}`}
          annotation={gameAnnotation.annotation}
          loading={gameAnnotation.loading}
          onSave={gameAnnotation.save}
          saveError={gameAnnotation.saveError}
          onAskClaude={(userComment) => {
            const { evalCp, bestMoveSan } = evalContextFor(mainlineFen)
            gameAnnotation.askClaude(evalCp, bestMoveSan, userComment)
          }}
          aiLoading={gameAnnotation.aiLoading}
          aiError={gameAnnotation.aiError}
          claudeKeyAvailable={claudeKeyAvailable}
        />
      )}

      <div className="mt-4 rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel-2)] p-4">
        <button
          type="button"
          disabled={analysing}
          onClick={() => boardFen && analyse(boardFen)}
          className="rounded border border-[var(--cw-copper)] px-3 py-1.5 font-condensed text-xs text-[var(--cw-copper)] disabled:opacity-50"
        >
          Analyse position
        </button>

        {analysisStatus === 'ok' && analysis && (
          <p className="mt-2 font-mono text-xs text-[var(--cw-text)]">
            {analysis.best_move_san ?? '—'}
            {analysis.eval_cp !== null && ` (eval ${analysis.eval_cp}cp)`}
            {analysis.pv.length > 0 && ` — ${analysis.pv.join(' ')}`}
            {analysis.depth !== null && ` (depth ${analysis.depth})`}
          </p>
        )}
        {analysisStatus === 'no_engine' && (
          <p className="mt-2 text-xs text-negative">
            Stockfish not found — configure it in Settings.
          </p>
        )}
        {analysisStatus === 'batch_running' && (
          <p className="mt-2 text-xs text-[var(--cw-muted)]">
            Batch analysis running — live engine paused until it finishes.
          </p>
        )}
        {analysisStatus === 'analysis_failed' && (
          <p className="mt-2 text-xs text-negative">
            This position couldn&apos;t be analysed. Try again.
          </p>
        )}
      </div>

      {!variation.active && (
        <GameReportPanel
          gameId={gameId ?? ''}
          opponentName={header.opponent_name}
          utcDate={header.utc_date}
        />
      )}

      {boardFen && (
        <BoardChatPanel
          gameId={gameId ?? ''}
          currentFen={boardFen}
          displayHistory={boardChat.displayHistory}
          conversationId={boardChat.conversationId}
          sending={boardChat.sending}
          error={boardChat.error}
          pastConversations={boardChat.pastConversations}
          sendMessage={boardChat.sendMessage}
          loadPastConversations={boardChat.loadPastConversations}
          resumeConversation={boardChat.resumeConversation}
          sendFeedback={boardChat.sendFeedback}
        />
      )}
    </div>
  )
}

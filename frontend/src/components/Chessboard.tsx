import { useEffect, useRef, useState } from 'react'
import { Chess } from 'chess.js'
import type { Move, Square } from 'chess.js'
import { Chessboard as ReactChessboard } from 'react-chessboard'

// Board rendering + sizing ported from
// dashboard/components/chessboard/frontend/src/index.jsx (dropping its
// Streamlit withStreamlitConnection bridge -- see the standing directive
// in docs/superpowers/specs/2026-07-13-game-detail-completion-design.md).
// Interactivity (drag/drop, click-to-move, the promotion picker, legal-
// move-square highlighting) is the SAME chess.js logic that vanilla
// component already ran client-side -- only the Streamlit bridge it
// reported through is gone. This component is a controlled component: it
// never keeps the resulting position in its own state after a move, only
// ephemeral UI state (selectedSquare, pendingPromotion) -- the parent
// owns position truth and passes a new `fen` back down.

const MIN_BOARD_WIDTH = 280
const MAX_BOARD_WIDTH = 560
const DEFAULT_BOARD_WIDTH = 420

// Copper-brown/parchment, not react-chessboard's default cream/green --
// see docs/superpowers/specs/2026-07-13-game-explorer-detail-design.md's
// Research section for the accessibility reasoning (medium-low contrast
// between squares, high contrast for pieces, avoid green blending).
const DARK_SQUARE_STYLE = { backgroundColor: '#8B5A2B' }
const LIGHT_SQUARE_STYLE = { backgroundColor: '#ECDFC8' }
const LASTMOVE_STYLE = { backgroundColor: 'rgba(255, 255, 102, 0.5)' }
const SELECTED_STYLE = { background: 'rgba(255, 255, 0, 0.4)' }

const PROMOTION_CHOICES: Array<{
  piece: 'q' | 'r' | 'b' | 'n'
  whiteGlyph: string
  blackGlyph: string
  label: string
}> = [
  { piece: 'q', whiteGlyph: '♕', blackGlyph: '♛', label: 'Queen' },
  { piece: 'r', whiteGlyph: '♖', blackGlyph: '♜', label: 'Rook' },
  { piece: 'b', whiteGlyph: '♗', blackGlyph: '♝', label: 'Bishop' },
  { piece: 'n', whiteGlyph: '♘', blackGlyph: '♞', label: 'Knight' },
]

export interface ChessMoveResult {
  uci: string
  fen: string
  san: string
}

interface PendingPromotion {
  from: Square
  to: Square
  previewFen: string
}

function getLegalMoveSquares(fen: string, square: Square): Record<string, React.CSSProperties> {
  const game = new Chess(fen)
  const moves = game.moves({ square, verbose: true })
  if (moves.length === 0) return {}
  const sourcePiece = game.get(square)
  const result: Record<string, React.CSSProperties> = {}
  for (const m of moves) {
    const targetPiece = game.get(m.to)
    const occupied = Boolean(targetPiece && sourcePiece && targetPiece.color !== sourcePiece.color)
    result[m.to] = {
      background: occupied
        ? 'radial-gradient(circle, rgba(0,0,0,.15) 85%, transparent 85%)'
        : 'radial-gradient(circle, rgba(0,0,0,.12) 25%, transparent 25%)',
      borderRadius: '50%',
    }
  }
  result[square] = SELECTED_STYLE
  return result
}

function isPromotionMove(fen: string, from: Square, to: Square): boolean {
  const game = new Chess(fen)
  const piece = game.get(from)
  if (!piece || piece.type !== 'p') return false
  return to[1] === '8' || to[1] === '1'
}

export default function Chessboard({
  fen,
  orientation,
  lastmoveFrom,
  lastmoveTo,
  arrows,
  highlightedSquares,
  interactive = false,
  onMove,
}: {
  fen?: string
  orientation: 'white' | 'black'
  lastmoveFrom: string | null
  lastmoveTo: string | null
  arrows?: Array<{ from: string; to: string; color?: string }>
  highlightedSquares?: Record<string, React.CSSProperties>
  interactive?: boolean
  onMove?: (move: ChessMoveResult) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [boardWidth, setBoardWidth] = useState(DEFAULT_BOARD_WIDTH)
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null)
  const [optionSquares, setOptionSquares] = useState<Record<string, React.CSSProperties>>({})
  const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const applyWidth = (containerWidth: number) => {
      const next = Math.max(MIN_BOARD_WIDTH, Math.min(MAX_BOARD_WIDTH, Math.floor(containerWidth)))
      setBoardWidth(next)
    }
    applyWidth(el.clientWidth || DEFAULT_BOARD_WIDTH)
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        applyWidth(entry.contentRect.width)
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Ephemeral UI state doesn't survive a position change from outside
  // (e.g. the parent stepping to a different variation move) -- without
  // this, a stale selection or open promotion picker could linger over
  // the wrong position.
  useEffect(() => {
    setSelectedSquare(null)
    setOptionSquares({})
    setPendingPromotion(null)
  }, [fen])

  if (!fen) return null

  function tryMove(from: Square, to: Square): boolean {
    if (pendingPromotion || !fen) return false

    if (isPromotionMove(fen, from, to)) {
      const probe = new Chess(fen)
      let legal: Move | null = null
      try {
        legal = probe.move({ from, to, promotion: 'q' })
      } catch {
        return false
      }
      if (!legal) return false
      setPendingPromotion({ from, to, previewFen: probe.fen() })
      setOptionSquares({})
      setSelectedSquare(null)
      return true
    }

    const copy = new Chess(fen)
    let move: Move | null = null
    try {
      move = copy.move({ from, to })
    } catch {
      return false
    }
    if (!move) return false
    setOptionSquares({})
    setSelectedSquare(null)
    onMove?.({ uci: move.from + move.to, fen: copy.fen(), san: move.san })
    return true
  }

  function completePromotion(pieceLetter: 'q' | 'r' | 'b' | 'n') {
    if (!pendingPromotion || !fen) return
    const { from, to } = pendingPromotion
    const copy = new Chess(fen)
    let move: Move | null = null
    try {
      move = copy.move({ from, to, promotion: pieceLetter })
    } catch {
      move = null
    }
    setPendingPromotion(null)
    if (!move) return
    onMove?.({ uci: move.from + move.to + (move.promotion ?? ''), fen: copy.fen(), san: move.san })
  }

  function onPieceDrop(sourceSquare: string, targetSquare: string): boolean {
    if (!interactive || pendingPromotion) return false
    return tryMove(sourceSquare as Square, targetSquare as Square)
  }

  function onSquareClick(square: string) {
    if (!interactive || pendingPromotion || !fen) return
    if (selectedSquare) {
      const moved = tryMove(selectedSquare, square as Square)
      if (moved) return
    }
    const game = new Chess(fen)
    const piece = game.get(square as Square)
    if (piece && piece.color === game.turn()) {
      setSelectedSquare(square as Square)
      setOptionSquares(getLegalMoveSquares(fen, square as Square))
    } else {
      setSelectedSquare(null)
      setOptionSquares({})
    }
  }

  const customSquareStyles: Record<string, React.CSSProperties> = {
    ...highlightedSquares,
    ...(lastmoveFrom ? { [lastmoveFrom]: LASTMOVE_STYLE } : {}),
    ...(lastmoveTo ? { [lastmoveTo]: LASTMOVE_STYLE } : {}),
    ...optionSquares,
  }

  const customArrows = (arrows ?? []).map(
    (a): [string, string, string | undefined] => [a.from, a.to, a.color],
  )

  const displayFen = pendingPromotion ? pendingPromotion.previewFen : fen
  // The promoting side is whoever just moved -- the pawn reaching the
  // last rank -- not whichever side's turn it is in the preview (already
  // flipped by chess.js's move()).
  const promotingColor = pendingPromotion && pendingPromotion.to[1] === '8' ? 'w' : 'b'

  return (
    <div ref={containerRef} style={{ width: '100%', position: 'relative' }}>
      <ReactChessboard
        position={displayFen}
        boardOrientation={orientation}
        boardWidth={boardWidth}
        arePiecesDraggable={interactive && !pendingPromotion}
        onPieceDrop={onPieceDrop}
        onSquareClick={onSquareClick}
        // react-chessboard 4.x has its OWN built-in promotion dialog that
        // auto-triggers on any pawn-to-last-rank drag (default
        // onPromotionCheck) and otherwise steals the drop before our
        // onPieceDrop's own promotion handling (tryMove/pendingPromotion)
        // ever runs -- found live: two competing promotion UIs, the
        // library's own dialog rendered and ours never did. We own
        // promotion detection ourselves, so tell it there's never one.
        onPromotionCheck={() => false}
        customSquareStyles={customSquareStyles}
        customArrows={customArrows}
        customDarkSquareStyle={DARK_SQUARE_STYLE}
        customLightSquareStyle={LIGHT_SQUARE_STYLE}
      />
      {pendingPromotion && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.4rem', marginTop: '0.5rem' }}>
          {PROMOTION_CHOICES.map(({ piece, whiteGlyph, blackGlyph, label }) => (
            <button
              key={piece}
              type="button"
              onClick={() => completePromotion(piece)}
              title={label}
              aria-label={`Promote to ${label}`}
              style={{
                fontSize: '1.6rem',
                lineHeight: 1,
                width: '2.4rem',
                height: '2.4rem',
                cursor: 'pointer',
                border: '1px solid #7A4423',
                borderRadius: '4px',
                background: '#EADFCF',
              }}
            >
              {promotingColor === 'w' ? whiteGlyph : blackGlyph}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

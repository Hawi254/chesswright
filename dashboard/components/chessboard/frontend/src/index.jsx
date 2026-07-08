import React, { useState, useEffect, useRef } from "react"
import ReactDOM from "react-dom/client"
import { Chessboard } from "react-chessboard"
import { Chess } from "chess.js"
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib"

const MIN_BOARD_WIDTH = 280
const MAX_BOARD_WIDTH = 560
const DEFAULT_BOARD_WIDTH = 420

const PROMOTION_CHOICES = [
  { piece: "q", whiteGlyph: "♕", blackGlyph: "♛", label: "Queen" },
  { piece: "r", whiteGlyph: "♖", blackGlyph: "♜", label: "Rook" },
  { piece: "b", whiteGlyph: "♗", blackGlyph: "♝", label: "Bishop" },
  { piece: "n", whiteGlyph: "♘", blackGlyph: "♞", label: "Knight" },
]

function ChessboardInner({ args, disabled }) {
  const {
    fen: propFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    orientation = "white",
    arrows = [],
    highlighted_squares: highlightedSquares = [],
    interactive = false,
    lastmove_from: lastmoveFrom = null,
    lastmove_to: lastmoveTo = null,
    enable_keyboard_nav: enableKeyboardNav = false,
  } = args

  const [game, setGame] = useState(() => {
    try { return new Chess(propFen) } catch { return new Chess() }
  })
  const [selectedSquare, setSelectedSquare] = useState(null)
  const [optionSquares, setOptionSquares] = useState({})
  // { from, to, previewFen } while the user is choosing a promotion piece --
  // previewFen shows the pawn already having arrived at the destination
  // (as a placeholder queen) so the board doesn't visually snap back while
  // waiting for a choice. Cleared once a piece is picked (or the pick fails).
  const [pendingPromotion, setPendingPromotion] = useState(null)

  const containerRef = useRef(null)
  const [boardWidth, setBoardWidth] = useState(DEFAULT_BOARD_WIDTH)

  // Monotonic per-mount event counter, stamped onto every emitted value as
  // "nonce". Lets Python tell a genuinely new event apart from Streamlit
  // re-delivering the component's last value on an unrelated rerun, without
  // needing a position-dependent `key` that forces a full iframe remount
  // (and the visible flash that comes with it) on every move/nav.
  const nonceRef = useRef(0)
  function nextNonce() {
    nonceRef.current += 1
    return nonceRef.current
  }

  // When Python changes propFen (ply navigation, variation step change),
  // reset the local board to match. Without this, useState only initialises
  // on mount, so piece positions stay stale while highlights update from props.
  useEffect(() => {
    try {
      setGame(new Chess(propFen))
      setSelectedSquare(null)
      setOptionSquares({})
      setPendingPromotion(null)
    } catch {
      // Invalid FEN -- keep current state rather than crashing.
    }
  }, [propFen])

  // Report height after every render so Streamlit sizes the iframe correctly.
  useEffect(() => { Streamlit.setFrameHeight() })

  // Size the board off its own container rather than a fixed pixel value --
  // the desktop window (pywebview) is user-resizable, and a hardcoded
  // boardWidth either wastes space on a large monitor or overflows a
  // narrower one. Clamped so it never grows absurdly large or shrinks below
  // a usable size.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const applyWidth = (containerWidth) => {
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

  // Grab keyboard focus on every mount when nav is enabled, not just once --
  // Game Detail's variation board remounts on every step (its `key` includes
  // var_step), and re-focusing on each mount is what keeps arrow-key
  // navigation working continuously rather than only for one keypress. Safe
  // to do unconditionally: if the user has since clicked into an unrelated
  // input (e.g. the annotation comment box), that input keeps focus until
  // the next remount -- this doesn't steal focus mid-typing.
  useEffect(() => {
    if (enableKeyboardNav) containerRef.current?.focus()
  }, [enableKeyboardNav])

  function getLegalMoveSquares(square) {
    const moves = game.moves({ square, verbose: true })
    if (!moves.length) return {}
    const result = {}
    moves.forEach(m => {
      const occupied = game.get(m.to) && game.get(m.to).color !== game.get(square)?.color
      result[m.to] = {
        background: occupied
          ? "radial-gradient(circle, rgba(0,0,0,.15) 85%, transparent 85%)"
          : "radial-gradient(circle, rgba(0,0,0,.12) 25%, transparent 25%)",
        borderRadius: "50%",
      }
    })
    result[square] = { background: "rgba(255, 255, 0, 0.4)" }
    return result
  }

  function isPromotionMove(from, to) {
    const piece = game.get(from)
    if (!piece || piece.type !== "p") return false
    return to[1] === "8" || to[1] === "1"
  }

  function tryMove(from, to) {
    if (pendingPromotion) return false

    if (isPromotionMove(from, to)) {
      // Verify legality before opening the picker -- an illegal
      // promotion-shaped drop (wrong pawn, blocked, still in check) must
      // snap back like any other illegal move, not open a picker for a
      // move that can't actually happen.
      const probe = new Chess(game.fen())
      let legal = null
      try { legal = probe.move({ from, to, promotion: "q" }) } catch { return false }
      if (!legal) return false
      setPendingPromotion({ from, to, previewFen: probe.fen() })
      setOptionSquares({})
      setSelectedSquare(null)
      return true
    }

    const copy = new Chess(game.fen())
    let move = null
    try { move = copy.move({ from, to }) } catch { return false }
    if (!move) return false
    setGame(copy)
    setOptionSquares({})
    setSelectedSquare(null)
    Streamlit.setComponentValue({
      type: "move",
      uci: move.from + move.to,
      fen: copy.fen(),
      san: move.san,
      nonce: nextNonce(),
    })
    return true
  }

  function completePromotion(pieceLetter) {
    if (!pendingPromotion) return
    const { from, to } = pendingPromotion
    const copy = new Chess(game.fen())
    let move = null
    try { move = copy.move({ from, to, promotion: pieceLetter }) } catch { move = null }
    setPendingPromotion(null)
    if (!move) return
    setGame(copy)
    Streamlit.setComponentValue({
      type: "move",
      uci: move.from + move.to + move.promotion,
      fen: copy.fen(),
      san: move.san,
      nonce: nextNonce(),
    })
  }

  function onKeyDown(e) {
    if (!enableKeyboardNav || pendingPromotion) return
    if (e.key === "ArrowLeft") {
      e.preventDefault()
      Streamlit.setComponentValue({ type: "nav", direction: "prev", nonce: nextNonce() })
    } else if (e.key === "ArrowRight") {
      e.preventDefault()
      Streamlit.setComponentValue({ type: "nav", direction: "next", nonce: nextNonce() })
    }
  }

  function onSquareClick(square) {
    if (!interactive || disabled || pendingPromotion) return
    if (selectedSquare) {
      const moved = tryMove(selectedSquare, square)
      if (moved) return
      // Didn't move — maybe clicking a new piece of the same color
    }
    const piece = game.get(square)
    if (piece && piece.color === game.turn()) {
      setSelectedSquare(square)
      setOptionSquares(getLegalMoveSquares(square))
    } else {
      setSelectedSquare(null)
      setOptionSquares({})
    }
  }

  function onPieceDrop(sourceSquare, targetSquare) {
    if (!interactive || disabled || pendingPromotion) return false
    return tryMove(sourceSquare, targetSquare)
  }

  const lastmoveStyle = { backgroundColor: "rgba(255, 255, 102, 0.5)" }
  const lastmoveSquares = selectedSquare ? {} : {
    ...(lastmoveFrom ? { [lastmoveFrom]: lastmoveStyle } : {}),
    ...(lastmoveTo   ? { [lastmoveTo]:   lastmoveStyle } : {}),
  }
  const chatHighlightStyles = Object.fromEntries(
    highlightedSquares.map(h => [h.square, { background: h.color }])
  )
  const customSquareStyles = { ...chatHighlightStyles, ...lastmoveSquares, ...optionSquares }

  // arrows prop: [{from, to, color}] dicts from Python
  const customArrows = arrows.map(a => [a.from, a.to, a.color || "rgb(0,128,0)"])

  const displayFen = pendingPromotion ? pendingPromotion.previewFen : game.fen()
  // The promoting side is whoever just moved -- the pawn that reached the
  // last rank, not game.turn() (which has already flipped in the preview).
  const promotingColor = pendingPromotion && pendingPromotion.to[1] === "8" ? "w" : "b"

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", width: "100%", outline: "none" }}
      tabIndex={enableKeyboardNav ? 0 : undefined}
      onKeyDown={enableKeyboardNav ? onKeyDown : undefined}
    >
      <Chessboard
        position={displayFen}
        onPieceDrop={onPieceDrop}
        onSquareClick={onSquareClick}
        boardOrientation={orientation}
        customArrows={customArrows}
        customSquareStyles={customSquareStyles}
        arePiecesDraggable={interactive && !disabled && !pendingPromotion}
        areArrowsAllowed={false}
        boardWidth={boardWidth}
      />
      {pendingPromotion && (
        <div style={{
          display: "flex",
          justifyContent: "center",
          gap: "0.4rem",
          marginTop: "0.5rem",
        }}>
          {PROMOTION_CHOICES.map(({ piece, whiteGlyph, blackGlyph, label }) => (
            <button
              key={piece}
              onClick={() => completePromotion(piece)}
              title={label}
              aria-label={`Promote to ${label}`}
              style={{
                fontSize: "1.6rem",
                lineHeight: 1,
                width: "2.4rem",
                height: "2.4rem",
                cursor: "pointer",
                border: "1px solid #7A4423",
                borderRadius: "4px",
                background: "#EADFCF",
              }}
            >
              {promotingColor === "w" ? whiteGlyph : blackGlyph}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const ChessboardComponent = withStreamlitConnection(ChessboardInner)

ReactDOM.createRoot(document.getElementById("root")).render(
  <ChessboardComponent />
)

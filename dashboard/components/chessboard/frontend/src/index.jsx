import React, { useState, useEffect } from "react"
import ReactDOM from "react-dom/client"
import { Chessboard } from "react-chessboard"
import { Chess } from "chess.js"
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib"

function ChessboardInner({ args, disabled }) {
  const {
    fen: propFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    orientation = "white",
    arrows = [],
    interactive = false,
    lastmove_from: lastmoveFrom = null,
    lastmove_to: lastmoveTo = null,
  } = args

  const [game, setGame] = useState(() => {
    try { return new Chess(propFen) } catch { return new Chess() }
  })
  const [selectedSquare, setSelectedSquare] = useState(null)
  const [optionSquares, setOptionSquares] = useState({})

  // When Python changes propFen (ply navigation, variation step change),
  // reset the local board to match. Without this, useState only initialises
  // on mount, so piece positions stay stale while highlights update from props.
  useEffect(() => {
    try {
      setGame(new Chess(propFen))
      setSelectedSquare(null)
      setOptionSquares({})
    } catch {
      // Invalid FEN -- keep current state rather than crashing.
    }
  }, [propFen])

  // Report height after every render so Streamlit sizes the iframe correctly.
  useEffect(() => { Streamlit.setFrameHeight() })

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

  function tryMove(from, to) {
    const copy = new Chess(game.fen())
    let move = null
    try { move = copy.move({ from, to, promotion: "q" }) } catch { return false }
    if (!move) return false
    setGame(copy)
    setOptionSquares({})
    setSelectedSquare(null)
    Streamlit.setComponentValue({
      uci: move.from + move.to + (move.promotion || ""),
      fen: copy.fen(),
      san: move.san,
    })
    return true
  }

  function onSquareClick(square) {
    if (!interactive || disabled) return
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
    if (!interactive || disabled) return false
    return tryMove(sourceSquare, targetSquare)
  }

  const lastmoveStyle = { backgroundColor: "rgba(255, 255, 102, 0.5)" }
  const lastmoveSquares = selectedSquare ? {} : {
    ...(lastmoveFrom ? { [lastmoveFrom]: lastmoveStyle } : {}),
    ...(lastmoveTo   ? { [lastmoveTo]:   lastmoveStyle } : {}),
  }
  const customSquareStyles = { ...lastmoveSquares, ...optionSquares }

  // arrows prop: [{from, to, color}] dicts from Python
  const customArrows = arrows.map(a => [a.from, a.to, a.color || "rgb(0,128,0)"])

  return (
    <Chessboard
      position={game.fen()}
      onPieceDrop={onPieceDrop}
      onSquareClick={onSquareClick}
      boardOrientation={orientation}
      customArrows={customArrows}
      customSquareStyles={customSquareStyles}
      arePiecesDraggable={interactive && !disabled}
      areArrowsAllowed={false}
      boardWidth={420}
    />
  )
}

const ChessboardComponent = withStreamlitConnection(ChessboardInner)

ReactDOM.createRoot(document.getElementById("root")).render(
  <ChessboardComponent />
)

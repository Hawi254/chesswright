import { useState } from 'react'
import { Chess } from 'chess.js'
import type { Move, Square } from 'chess.js'
import { API_BASE } from '../lib/apiBase'
import type { SavedVariation } from './useSavedVariations'

export interface VariationMoveResult {
  uci: string
  fen: string
  san: string
}

export interface UseVariationResult {
  active: boolean
  variationId: string | null
  branchPly: number | null
  moves: string[]
  sans: string[]
  step: number
  currentFen: string | null
  lastMoveSquares: { from: string; to: string } | null
  applyMove: (currentPly: number, currentMainlineFen: string, move: VariationMoveResult) => void
  stepTo: (n: number) => void
  exit: () => void
  discard: () => void
  load: (variation: SavedVariation) => void
}

interface VariationState {
  active: boolean
  variationId: string | null
  branchPly: number | null
  moves: string[]
  sans: string[]
  fens: string[]
  step: number
}

const INITIAL_STATE: VariationState = {
  active: false,
  variationId: null,
  branchPly: null,
  moves: [],
  sans: [],
  fens: [],
  step: 0,
}

function squaresFromUci(uci: string): { from: string; to: string } {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) }
}

export function useVariation(gameId: string, onMutated?: () => void): UseVariationResult {
  const [state, setState] = useState<VariationState>(INITIAL_STATE)

  function applyMove(currentPly: number, currentMainlineFen: string, move: VariationMoveResult) {
    if (!state.active) {
      const branchFen = currentMainlineFen
      const moves = [move.uci]
      setState({
        active: true,
        variationId: null,
        branchPly: currentPly,
        moves,
        sans: [move.san],
        fens: [branchFen, move.fen],
        step: 1,
      })
      fetch(`${API_BASE}/api/games/${gameId}/variations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_ply: currentPly, branch_fen: branchFen, moves }),
      })
        .then((r) => r.json())
        .then((body: { id: string }) => {
          // Guards against a rare race: exiting/discarding and starting a
          // brand-new variation before this response lands. Doesn't fully
          // disambiguate "still the same variation" from "a new one" --
          // acceptable given how narrow the window is (see the design
          // spec's Open items); not worth a request-generation counter.
          setState((cur) => (cur.active ? { ...cur, variationId: body.id } : cur))
          onMutated?.()
        })
        .catch(() => {})
      return
    }

    const moves = [...state.moves.slice(0, state.step), move.uci]
    setState({
      ...state,
      moves,
      sans: [...state.sans.slice(0, state.step), move.san],
      fens: [...state.fens.slice(0, state.step + 1), move.fen],
      step: state.step + 1,
    })
    if (state.variationId) {
      fetch(`${API_BASE}/api/variations/${state.variationId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ moves }),
      }).catch(() => {})
    }
  }

  function stepTo(n: number) {
    setState((prev) => {
      if (!prev.active) return prev
      const clamped = Math.max(0, Math.min(n, prev.moves.length))
      return { ...prev, step: clamped }
    })
  }

  function exit() {
    setState(INITIAL_STATE)
  }

  function discard() {
    setState((prev) => {
      if (prev.variationId) {
        fetch(`${API_BASE}/api/variations/${prev.variationId}`, { method: 'DELETE' }).catch(() => {})
      }
      return INITIAL_STATE
    })
    onMutated?.()
  }

  function load(variation: SavedVariation) {
    const board = new Chess(variation.branch_fen)
    const moves: string[] = []
    const sans: string[] = []
    const fens: string[] = [variation.branch_fen]
    for (const uci of variation.moves) {
      const from = uci.slice(0, 2) as Square
      const to = uci.slice(2, 4) as Square
      const promotion = uci.length > 4 ? uci.slice(4) : undefined
      let move: Move | null = null
      try {
        move = board.move({ from, to, promotion })
      } catch {
        move = null
      }
      if (!move) break
      moves.push(uci)
      sans.push(move.san)
      fens.push(board.fen())
    }
    setState({
      active: true,
      variationId: variation.id,
      branchPly: variation.branch_ply,
      moves,
      sans,
      fens,
      step: moves.length,
    })
  }

  const currentFen = state.active ? state.fens[state.step] : null
  const lastMoveSquares =
    state.active && state.step > 0 ? squaresFromUci(state.moves[state.step - 1]) : null

  return {
    active: state.active,
    variationId: state.variationId,
    branchPly: state.branchPly,
    moves: state.moves,
    sans: state.sans,
    step: state.step,
    currentFen,
    lastMoveSquares,
    applyMove,
    stepTo,
    exit,
    discard,
    load,
  }
}

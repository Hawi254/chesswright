import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface PieceMovementRow {
  piece: string
  piece_name: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface PieceByViewRow {
  piece: string
  piece_name: string
  phase?: string
  bucket?: string
  n_moves: number
  blunder_rate: number
}

export interface BishopSquareColorRow {
  square_color: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface RookKingBackrankRow {
  piece: string
  piece_name: string
  location: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface SquareHeatmapCell {
  file: string
  rank: number
  blunder_rate: number
  n_moves: number
}

export interface SquareHeatmap {
  cells: SquareHeatmapCell[]
  n_analyzed: number
  n_total_in_scope: number
}

export interface CastlingWinRow {
  status: string
  n_games: number
  win_pct: number
}

export interface CastlingAcplRow {
  status: string
  n_games: number
  n_moves: number
  acpl: number
}

export interface PatternsPiecesData {
  piece_movement: PieceMovementRow[]
  piece_by_view: PieceByViewRow[]
  bishop_square_color: BishopSquareColorRow[]
  rook_king_backrank: RookKingBackrankRow[]
  square_heatmap: SquareHeatmap
  motif_backfill_needed: boolean
  castling: { win: CastlingWinRow[]; acpl: CastlingAcplRow[] }
}

export interface UsePatternsPiecesResult {
  data: PatternsPiecesData | null
  loading: boolean
  error: boolean
}

export function usePatternsPieces(viewBy: 'phase' | 'sharpness'): UsePatternsPiecesResult {
  const [state, setState] = useState<UsePatternsPiecesResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState({ data: null, loading: true, error: false })
    fetch(`${API_BASE}/api/patterns/pieces?view_by=${viewBy}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsPiecesData>
      })
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: false })
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false, error: true })
      })
    return () => {
      cancelled = true
    }
  }, [viewBy])

  return state
}

import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/apiBase'

export interface SharpnessRow {
  bucket: string
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface MaterialStructureRow {
  label: string
  n_games: number
  win_pct: number
  draw_pct: number
  loss_pct: number
  acpl: number | null
  n_analyzed: number
}

export interface MaterialStructure {
  rows: MaterialStructureRow[]
  label_header: string
  n_unanalyzed: number
}

export interface BishopEndingRow {
  bucket: string
  n_moves: number
  acpl: number
}

export interface BucketWinRow {
  bucket: string
  n_games: number
  win_pct: number
}

export interface BucketAcplRow {
  bucket: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface SymmetricWinRow {
  symmetry_label: string
  n_games: number
  win_pct: number
}

export interface SymmetricAcplRow {
  symmetry_label: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface PositionCharacter {
  bucket_win: BucketWinRow[]
  bucket_acpl: BucketAcplRow[]
  symmetric_win: SymmetricWinRow[]
  symmetric_acpl: SymmetricAcplRow[]
  central_tension_pct: number | null
  n_classified: number
  n_total_games: number
}

export interface CastlingWinRow {
  castling_config: string
  n_games: number
  win_pct: number
}

export interface CastlingAcplRow {
  castling_config: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface ActionWinRow {
  action_side: string
  n_games: number
  win_pct: number
}

export interface ActionAcplRow {
  action_side: string
  n_games: number
  n_moves: number
  acpl: number
  blunder_rate: number
}

export interface GameSide {
  castling_win: CastlingWinRow[]
  castling_acpl: CastlingAcplRow[]
  action_win: ActionWinRow[]
  action_acpl: ActionAcplRow[]
}

export interface PatternsPositionsData {
  sharpness: SharpnessRow[]
  material_structure: MaterialStructure
  bishop_endings: BishopEndingRow[]
  position_character: PositionCharacter
  game_side: GameSide
}

export interface UsePatternsPositionsResult {
  data: PatternsPositionsData | null
  loading: boolean
  error: boolean
}

export function usePatternsPositions(
  structureType: 'endgame' | 'middlegame',
  grouped: boolean,
): UsePatternsPositionsResult {
  const [state, setState] = useState<UsePatternsPositionsResult>({ data: null, loading: true, error: false })

  useEffect(() => {
    let cancelled = false
    setState({ data: null, loading: true, error: false })
    fetch(`${API_BASE}/api/patterns/positions?structure_type=${structureType}&grouped=${grouped}`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PatternsPositionsData>
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
  }, [structureType, grouped])

  return state
}

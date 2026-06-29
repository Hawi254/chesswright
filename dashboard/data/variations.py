"""CRUD for saved game variations and per-move annotations (v0.1.12)."""
import dataclasses
import json
import uuid

import chess


@dataclasses.dataclass
class Variation:
    id: str
    game_id: str
    branch_ply: int
    branch_fen: str
    moves: list
    title: str | None
    created_at: str
    updated_at: str


@dataclasses.dataclass
class Annotation:
    id: str
    variation_id: str
    move_index: int
    glyph: str | None
    comment: str | None
    ai_comment: str | None
    ai_model: str | None
    generated_at: str | None


def compute_variation_fen(branch_fen: str, moves_uci: list, step: int) -> str:
    """Replay UCI moves onto branch_fen up to `step` and return the resulting FEN.

    Returns branch_fen unchanged if any move in the sequence is illegal — this
    prevents a hard crash if a stale or invalid UCI somehow ends up in the list.
    """
    board = chess.Board(branch_fen)
    for uci in moves_uci[:step]:
        try:
            board.push_uci(uci)
        except Exception:
            return board.fen()
    return board.fen()


def save_variation(sqlite_conn, game_id: str, branch_ply: int,
                   branch_fen: str, moves: list) -> str:
    """Persist a new variation; return its UUID."""
    vid = str(uuid.uuid4())
    sqlite_conn.execute("""
        INSERT INTO variations (id, game_id, branch_ply, branch_fen, moves_json)
        VALUES (?, ?, ?, ?, ?)
    """, [vid, game_id, branch_ply, branch_fen, json.dumps(moves)])
    sqlite_conn.commit()
    return vid


def update_variation_moves(sqlite_conn, variation_id: str, moves: list) -> None:
    sqlite_conn.execute("""
        UPDATE variations SET moves_json = ?, updated_at = datetime('now') WHERE id = ?
    """, [json.dumps(moves), variation_id])
    sqlite_conn.commit()


def delete_variation(sqlite_conn, variation_id: str) -> None:
    sqlite_conn.execute("DELETE FROM variations WHERE id = ?", [variation_id])
    sqlite_conn.commit()


def list_variations(sqlite_conn, game_id: str) -> list:
    rows = sqlite_conn.execute("""
        SELECT id, game_id, branch_ply, branch_fen, moves_json, title, created_at, updated_at
        FROM variations WHERE game_id = ? ORDER BY created_at DESC
    """, [game_id]).fetchall()
    return [Variation(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6], r[7]) for r in rows]


def get_variation_annotations(sqlite_conn, variation_id: str) -> dict:
    """Return {move_index: Annotation} for all annotated positions in a variation."""
    rows = sqlite_conn.execute("""
        SELECT id, variation_id, move_index, glyph, comment, ai_comment, ai_model, generated_at
        FROM variation_annotations WHERE variation_id = ? ORDER BY move_index
    """, [variation_id]).fetchall()
    return {r[2]: Annotation(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows}


def upsert_annotation(sqlite_conn, variation_id: str, move_index: int, *,
                      glyph=None, comment=None, ai_comment=None, ai_model=None) -> None:
    """Insert or update an annotation row; only supplied fields overwrite stored ones."""
    aid = str(uuid.uuid4())
    sqlite_conn.execute("""
        INSERT INTO variation_annotations
            (id, variation_id, move_index, glyph, comment, ai_comment, ai_model, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?,
            CASE WHEN ? IS NOT NULL THEN datetime('now') ELSE NULL END)
        ON CONFLICT (variation_id, move_index) DO UPDATE SET
            glyph        = COALESCE(excluded.glyph,       glyph),
            comment      = COALESCE(excluded.comment,     comment),
            ai_comment   = COALESCE(excluded.ai_comment,  ai_comment),
            ai_model     = COALESCE(excluded.ai_model,    ai_model),
            generated_at = CASE WHEN excluded.ai_comment IS NOT NULL
                                THEN datetime('now') ELSE generated_at END
    """, [aid, variation_id, move_index,
          glyph, comment, ai_comment, ai_model,
          ai_comment])
    sqlite_conn.commit()

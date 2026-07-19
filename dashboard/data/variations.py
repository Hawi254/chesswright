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
    """A glyph/comment/AI-comment attached to one position. Belongs to
    exactly one of a variation (variation_id set) or a mainline game
    (game_id set) -- never both. Both are optional, defaulted fields
    (rather than two dataclasses) so callers on both sides construct
    the same type; see the Slice 4 design spec's "Open items"."""
    id: str
    move_index: int
    glyph: str | None
    comment: str | None
    ai_comment: str | None
    ai_model: str | None
    generated_at: str | None
    variation_id: str | None = None
    game_id: str | None = None


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
    # created_at has only second resolution, so two variations saved within
    # the same second tie; rowid (monotonic insertion order, since id is a
    # TEXT PRIMARY KEY and doesn't replace it) breaks the tie deterministically.
    rows = sqlite_conn.execute("""
        SELECT id, game_id, branch_ply, branch_fen, moves_json, title, created_at, updated_at
        FROM variations WHERE game_id = ? ORDER BY created_at DESC, rowid DESC
    """, [game_id]).fetchall()
    return [Variation(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6], r[7]) for r in rows]


def get_variation(sqlite_conn, variation_id: str) -> Variation | None:
    """Single-row lookup by id; None if the variation doesn't exist."""
    row = sqlite_conn.execute("""
        SELECT id, game_id, branch_ply, branch_fen, moves_json, title, created_at, updated_at
        FROM variations WHERE id = ?
    """, [variation_id]).fetchone()
    if row is None:
        return None
    return Variation(row[0], row[1], row[2], row[3], json.loads(row[4]), row[5], row[6], row[7])


def get_variation_annotations(sqlite_conn, variation_id: str) -> dict:
    """Return {move_index: Annotation} for all annotated positions in a variation."""
    rows = sqlite_conn.execute("""
        SELECT id, move_index, glyph, comment, ai_comment, ai_model, generated_at
        FROM variation_annotations WHERE variation_id = ? ORDER BY move_index
    """, [variation_id]).fetchall()
    return {
        r[1]: Annotation(id=r[0], move_index=r[1], glyph=r[2], comment=r[3],
                         ai_comment=r[4], ai_model=r[5], generated_at=r[6],
                         variation_id=variation_id)
        for r in rows
    }


def get_variation_annotation(sqlite_conn, variation_id: str, move_index: int) -> Annotation | None:
    """Single-row lookup; None if unannotated. get_variation_annotations()
    returns the whole-variation dict, which the per-position endpoint
    doesn't need."""
    row = sqlite_conn.execute("""
        SELECT id, move_index, glyph, comment, ai_comment, ai_model, generated_at
        FROM variation_annotations WHERE variation_id = ? AND move_index = ?
    """, [variation_id, move_index]).fetchone()
    if row is None:
        return None
    return Annotation(id=row[0], move_index=row[1], glyph=row[2], comment=row[3],
                      ai_comment=row[4], ai_model=row[5], generated_at=row[6],
                      variation_id=variation_id)


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

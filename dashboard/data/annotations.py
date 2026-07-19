"""CRUD for mainline (non-variation) per-position annotations. Separate
storage from variation_annotations/variations.py -- see
docs/superpowers/specs/2026-07-14-game-detail-slice4-annotations-design.md
"Backend: mainline annotations" for why. Copied 1:1 from variations.py's
upsert_annotation/get_variation_annotations SQL shape, re-keyed on
(game_id, ply) instead of (variation_id, move_index)."""
import uuid

from .variations import Annotation


def get_game_annotations(sqlite_conn, game_id: str) -> dict:
    """Return {ply: Annotation} for all annotated positions in a game."""
    rows = sqlite_conn.execute("""
        SELECT id, ply, glyph, comment, ai_comment, ai_model, generated_at
        FROM game_annotations WHERE game_id = ? ORDER BY ply
    """, [game_id]).fetchall()
    return {
        r[1]: Annotation(id=r[0], move_index=r[1], glyph=r[2], comment=r[3],
                         ai_comment=r[4], ai_model=r[5], generated_at=r[6],
                         game_id=game_id)
        for r in rows
    }


def get_game_annotation(sqlite_conn, game_id: str, ply: int) -> Annotation | None:
    """Single-row lookup; None if unannotated."""
    row = sqlite_conn.execute("""
        SELECT id, ply, glyph, comment, ai_comment, ai_model, generated_at
        FROM game_annotations WHERE game_id = ? AND ply = ?
    """, [game_id, ply]).fetchone()
    if row is None:
        return None
    return Annotation(id=row[0], move_index=row[1], glyph=row[2], comment=row[3],
                      ai_comment=row[4], ai_model=row[5], generated_at=row[6],
                      game_id=game_id)


def upsert_game_annotation(sqlite_conn, game_id: str, ply: int, *,
                            glyph=None, comment=None, ai_comment=None, ai_model=None) -> None:
    """Insert or update an annotation row; only supplied fields overwrite stored ones."""
    aid = str(uuid.uuid4())
    sqlite_conn.execute("""
        INSERT INTO game_annotations
            (id, game_id, ply, glyph, comment, ai_comment, ai_model, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?,
            CASE WHEN ? IS NOT NULL THEN datetime('now') ELSE NULL END)
        ON CONFLICT (game_id, ply) DO UPDATE SET
            glyph        = COALESCE(excluded.glyph,       glyph),
            comment      = COALESCE(excluded.comment,     comment),
            ai_comment   = COALESCE(excluded.ai_comment,  ai_comment),
            ai_model     = COALESCE(excluded.ai_model,    ai_model),
            generated_at = CASE WHEN excluded.ai_comment IS NOT NULL
                                THEN datetime('now') ELSE generated_at END
    """, [aid, game_id, ply, glyph, comment, ai_comment, ai_model, ai_comment])
    sqlite_conn.commit()

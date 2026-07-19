"""GET/PUT/POST /api/variations/{variation_id}/annotations/{move_index} and
/api/games/{game_id}/annotations/{ply} -- glyph/comment annotations plus
Claude-generated ai-comments, for both a saved variation and the game's own
move list (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import dataclasses

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import get_db_connections

import claude_narrative
import data

router = APIRouter()


class UpsertAnnotationRequest(BaseModel):
    glyph: str | None = None
    comment: str | None = None


class AiCommentRequest(BaseModel):
    fen: str
    eval_cp: int | None = None
    best_move_san: str | None = None
    user_comment: str | None = None


@router.get("/api/variations/{variation_id}/annotations/{move_index}")
def get_variation_annotation_endpoint(variation_id: str, move_index: int):
    sqlite_conn, _ = get_db_connections()
    annotation = data.get_variation_annotation(sqlite_conn, variation_id, move_index)
    return dataclasses.asdict(annotation) if annotation else None


@router.put("/api/variations/{variation_id}/annotations/{move_index}")
def put_variation_annotation(variation_id: str, move_index: int, body: UpsertAnnotationRequest):
    sqlite_conn, _ = get_db_connections()
    data.upsert_annotation(sqlite_conn, variation_id, move_index,
                           glyph=body.glyph, comment=body.comment)
    annotation = data.get_variation_annotation(sqlite_conn, variation_id, move_index)
    return dataclasses.asdict(annotation)


@router.post("/api/variations/{variation_id}/annotations/{move_index}/ai-comment")
def variation_ai_comment(variation_id: str, move_index: int, body: AiCommentRequest):
    sqlite_conn, _ = get_db_connections()
    try:
        ai_text = claude_narrative.annotate_position(
            fen=body.fen, eval_cp=body.eval_cp,
            engine_best_san=body.best_move_san, user_comment=body.user_comment,
        )
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")

    data.upsert_annotation(sqlite_conn, variation_id, move_index,
                           ai_comment=ai_text, ai_model=claude_narrative.MODEL)
    annotation = data.get_variation_annotation(sqlite_conn, variation_id, move_index)
    return dataclasses.asdict(annotation)


@router.get("/api/games/{game_id}/annotations/{ply}")
def get_game_annotation_endpoint(game_id: str, ply: int):
    sqlite_conn, _ = get_db_connections()
    annotation = data.get_game_annotation(sqlite_conn, game_id, ply)
    return dataclasses.asdict(annotation) if annotation else None


@router.put("/api/games/{game_id}/annotations/{ply}")
def put_game_annotation(game_id: str, ply: int, body: UpsertAnnotationRequest):
    sqlite_conn, _ = get_db_connections()
    data.upsert_game_annotation(sqlite_conn, game_id, ply,
                                glyph=body.glyph, comment=body.comment)
    annotation = data.get_game_annotation(sqlite_conn, game_id, ply)
    return dataclasses.asdict(annotation)


@router.post("/api/games/{game_id}/annotations/{ply}/ai-comment")
def game_ai_comment(game_id: str, ply: int, body: AiCommentRequest):
    sqlite_conn, _ = get_db_connections()
    try:
        ai_text = claude_narrative.annotate_position(
            fen=body.fen, eval_cp=body.eval_cp,
            engine_best_san=body.best_move_san, user_comment=body.user_comment,
        )
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")

    data.upsert_game_annotation(sqlite_conn, game_id, ply,
                                ai_comment=ai_text, ai_model=claude_narrative.MODEL)
    annotation = data.get_game_annotation(sqlite_conn, game_id, ply)
    return dataclasses.asdict(annotation)

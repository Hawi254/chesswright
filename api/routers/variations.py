"""POST/PUT/DELETE/GET /api/games/{game_id}/variations and
/api/variations/{variation_id}[/pgn] -- create/update/delete/list saved
variations off a game (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import dataclasses

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.db import get_db_connections

import chess_display
import data

router = APIRouter()


class CreateVariationRequest(BaseModel):
    branch_ply: int
    branch_fen: str
    moves: list[str]


class UpdateVariationRequest(BaseModel):
    moves: list[str]


@router.post("/api/games/{game_id}/variations")
def create_variation(game_id: str, body: CreateVariationRequest):
    sqlite_conn, _ = get_db_connections()
    variation_id = data.save_variation(
        sqlite_conn, game_id, body.branch_ply, body.branch_fen, body.moves)
    return {"id": variation_id}


@router.put("/api/variations/{variation_id}")
def update_variation(variation_id: str, body: UpdateVariationRequest):
    sqlite_conn, _ = get_db_connections()
    data.update_variation_moves(sqlite_conn, variation_id, body.moves)
    return {"ok": True}


@router.delete("/api/variations/{variation_id}")
def delete_variation(variation_id: str):
    sqlite_conn, _ = get_db_connections()
    data.delete_variation(sqlite_conn, variation_id)
    return {"ok": True}


@router.get("/api/games/{game_id}/variations")
def list_variations(game_id: str):
    sqlite_conn, _ = get_db_connections()
    variations = data.list_variations(sqlite_conn, game_id)
    return [dataclasses.asdict(v) for v in variations]


@router.get("/api/variations/{variation_id}/pgn")
def variation_pgn(variation_id: str):
    sqlite_conn, _ = get_db_connections()
    variation = data.get_variation(sqlite_conn, variation_id)
    if variation is None:
        raise HTTPException(status_code=404, detail="Variation not found")

    annotations = data.get_variation_annotations(sqlite_conn, variation_id)
    pgn_text = chess_display.variation_to_pgn(
        variation.branch_fen, variation.moves, annotations, title=variation.title)
    safe_title = (variation.title or f"var_{variation.id[:8]}").replace(" ", "_")
    return Response(
        content=pgn_text,
        media_type="application/x-chess-pgn",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.pgn"'},
    )

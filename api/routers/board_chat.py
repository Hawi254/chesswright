"""GET/POST /api/games/{game_id}/board-chat/* and
/api/board-chat/turns/{turn_id}/feedback -- Pro-gated in-context chat about
a specific game/position (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import get_db_connections

import claude_narrative
import pro_gate
from data import board_chat as data_board_chat

router = APIRouter()


class BoardChatTurnRequest(BaseModel):
    conversation_id: int | None = None
    question: str
    current_fen: str


class BoardChatFeedbackRequest(BaseModel):
    feedback: int
    question_summary: str | None = None


@router.get("/api/games/{game_id}/board-chat/conversations")
def list_board_chat_conversations(game_id: str):
    sqlite_conn, _ = get_db_connections()
    return {"conversations": data_board_chat.list_conversations_for_game(sqlite_conn, game_id)}


@router.get("/api/games/{game_id}/board-chat/conversations/{conversation_id}")
def resume_board_chat_conversation(game_id: str, conversation_id: int, current_fen: str):
    sqlite_conn, _ = get_db_connections()
    try:
        from chesswright_pro import board_chat
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")
    return board_chat.resume_conversation(sqlite_conn, conversation_id, current_fen)


@router.post("/api/games/{game_id}/board-chat/turns")
def post_board_chat_turn(game_id: str, body: BoardChatTurnRequest):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import board_chat
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")

    sqlite_conn, duck_conn = get_db_connections()
    conversation_id = body.conversation_id
    if conversation_id is None:
        conversation_id = data_board_chat.start_conversation(sqlite_conn, game_id)
    try:
        result = board_chat.run_chat_turn(
            duck_conn, sqlite_conn, game_id, conversation_id, body.question, body.current_fen)
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    return {"conversation_id": conversation_id, **result}


@router.post("/api/board-chat/turns/{turn_id}/feedback")
def post_board_chat_feedback(turn_id: int, body: BoardChatFeedbackRequest):
    sqlite_conn, _ = get_db_connections()
    try:
        data_board_chat.record_feedback(sqlite_conn, turn_id, body.feedback)
    except ValueError as e:
        # "no board_chat_turns row with id=..." is the ONLY ValueError shape
        # for a genuinely missing resource (matches Game Report's own
        # IndexError -> 404 precedent for "the id you named doesn't exist");
        # the other two ValueError shapes (feedback on a non-assistant turn,
        # an out-of-range feedback value) are the caller's own malformed
        # input, not a missing resource.
        if str(e).startswith("no board_chat_turns row"):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    if body.feedback == -1 and body.question_summary:
        data_board_chat.record_capability_gap(
            sqlite_conn, turn_id, body.question_summary,
            "player marked this answer unhelpful")
    return {"ok": True}

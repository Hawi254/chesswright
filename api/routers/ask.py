"""POST /api/ask/stream -- the free-form "Ask" page's SSE-streamed Claude
answer (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.cache import TTLCache
from api.db import get_db_connections

import claude_narrative
import data

router = APIRouter()

_ask_brief_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _ask_brief_cache.clear()


class AskRequest(BaseModel):
    question: str


@router.post("/api/ask/stream")
def ask_stream(payload: AskRequest):
    if not claude_narrative.api_key_available():
        raise HTTPException(
            status_code=503,
            detail="No Anthropic API key configured. Add your own key on the Settings page to enable this feature.",
        )

    sqlite_conn, duck_conn = get_db_connections()
    brief = _ask_brief_cache.get(lambda: data.build_ask_data_brief(duck_conn, sqlite_conn))

    def event_stream():
        chunks = []
        try:
            for delta in claude_narrative.answer_question_stream(payload.question, brief):
                chunks.append(delta)
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return
        yield f"data: {json.dumps({'done': True, 'answer': ''.join(chunks)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

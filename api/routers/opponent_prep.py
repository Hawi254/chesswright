"""POST/GET /api/opponent-prep/* -- scouting-run controls plus the
per-opponent report, notes, and tournament-report pages (moved from
api/main.py, docs/superpowers/specs/2026-07-17-api-main-router-split-
design.md).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import claude_narrative
import data
import joblock
import opponent_prep_runner
import pro_gate
from api.serialization import _narrative_response
from connections import resolve_db_path

router = APIRouter()


class StartOpponentPrepRequest(BaseModel):
    username: str
    n_games: int


@router.post("/api/opponent-prep/start")
def start_opponent_prep(body: StartOpponentPrepRequest):
    try:
        opponent_prep_runner.start(body.username, body.n_games)
    except (RuntimeError, joblock.LockHeldError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


@router.get("/api/opponent-prep/status")
def opponent_prep_status():
    state = opponent_prep_runner.get_state()
    return {
        "status": state.get("status", "idle"),
        "username": state.get("username"),
        "step": state.get("step"),
        "error": state.get("error"),
    }


@router.post("/api/opponent-prep/stop")
def stop_opponent_prep():
    opponent_prep_runner.stop()
    return {"ok": True}


@router.get("/api/opponent-prep/list")
def list_opponent_prep():
    return {"opponents": data.list_scouted_opponents(resolve_db_path())}


@router.get("/api/opponent-prep/report/{username}")
def opponent_prep_report(username: str):
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        raise HTTPException(status_code=404, detail=f"No analysis data found for {username}")
    try:
        summary = data.get_scout_summary(duck_conn)
        repertoire_df = data.get_repertoire(duck_conn)
        return {
            "gamesAnalyzed": summary["games_analyzed"],
            "colorSplit": summary["color_split"],
            "dateRange": summary["date_range"],
            "repertoire": repertoire_df.to_dict(orient="records"),
        }
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass


@router.get("/api/opponent-prep/{username}/notes")
def get_opponent_prep_notes(username: str):
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        raise HTTPException(status_code=404, detail=f"No analysis data found for {username}")
    try:
        return _narrative_response(data.get_cached_narrative(sqlite_conn, "opponent_prep_notes", username))
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass


@router.post("/api/opponent-prep/{username}/notes/generate")
def generate_opponent_prep_notes(username: str):
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        raise HTTPException(status_code=404, detail=f"No analysis data found for {username}")
    try:
        summary = data.get_scout_summary(duck_conn)
        repertoire_df = data.get_repertoire(duck_conn)
        try:
            response_text = claude_narrative.generate_scouting_notes(
                username, repertoire_df, summary["games_analyzed"])
        except claude_narrative.MissingApiKeyError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
        data.save_narrative(sqlite_conn, "opponent_prep_notes", username, response_text, claude_narrative.MODEL)
        return {"narrative": response_text}
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass


@router.get("/api/opponent-prep/{username}/tournament-report")
def get_opponent_prep_tournament_report(username: str):
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        raise HTTPException(status_code=404, detail=f"No analysis data found for {username}")
    try:
        cached = data.get_cached_narrative(sqlite_conn, "tournament_prep", username)
        if cached is None:
            return {"report_html": None, "generated_at": None}
        report_html_str, generated_at = cached
        return {"report_html": report_html_str, "generated_at": generated_at}
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass


@router.post("/api/opponent-prep/{username}/tournament-report/generate")
def generate_opponent_prep_tournament_report(username: str):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import tournament_prep
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")

    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        raise HTTPException(status_code=404, detail=f"No analysis data found for {username}")
    try:
        summary = data.get_scout_summary(duck_conn)
        repertoire_df = data.get_repertoire(duck_conn)
        from api.db import get_db_connections
        _, main_duck_conn = get_db_connections()
        report_html_str = tournament_prep.generate_report(
            username, summary["games_analyzed"], repertoire_df, main_duck_conn)
        # "n/a": this row was built from data.get_repertoire()'s own query
        # + chesswright_pro's report template, never a Claude API call --
        # unlike every other row in claude_narratives, `model` here does
        # not name an LLM.
        data.save_narrative(sqlite_conn, "tournament_prep", username, report_html_str, "n/a")
        cached = data.get_cached_narrative(sqlite_conn, "tournament_prep", username)
        _, generated_at = cached
        return {"report_html": report_html_str, "generated_at": generated_at}
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass


@router.get("/api/opponent-prep/{username}/tournament-report/download.html")
def download_opponent_prep_tournament_report_html(username: str):
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        raise HTTPException(status_code=404, detail=f"No analysis data found for {username}")
    try:
        cached = data.get_cached_narrative(sqlite_conn, "tournament_prep", username)
        if cached is None:
            raise HTTPException(status_code=404, detail="No report generated yet")
        report_html_str, _ = cached
        safe_username = username.replace(" ", "_")
        filename = f"chesswright_prep_{safe_username}.html"
        return Response(
            content=report_html_str, media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass

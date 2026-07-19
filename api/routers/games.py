"""GET /api/games/explorer, GET /api/games/{game_id}[/report...], and POST
/api/analyse-position -- the game list, single-game detail view, its Pro
game-report, and the interactive engine-analysis endpoint the game-detail
board's PositionInspector calls (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import json

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe

import chess_display
import claude_narrative
import config
import data
import engine_status
import joblock
import lichess_cloud_eval
import narrative
import pro_gate
import report_html

router = APIRouter()

_game_explorer_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _game_explorer_cache.clear()


def _compute_game_explorer_rows():
    """Shared by /api/games/explorer and, via the same cache instance,
    /api/games/{game_id}'s badge lookup (Task 2) -- mirrors
    game_detail_view.py's own approach of reusing the cached explorer
    table for a single game's badges rather than a second query."""
    _, duck_conn = get_db_connections()
    df = data.get_game_explorer_table(duck_conn)
    df = df.copy()
    # Guard the empty-DB case explicitly rather than calling df.apply(...,
    # axis=1) unconditionally: pandas returns a DataFrame (not a Series)
    # from a row-wise apply on a 0-row frame, which breaks the column
    # assignment below (see the pandas_empty_df_apply_axis1_gotcha project
    # memory -- hit once already in this codebase's Python layer, avoided
    # here before it could repeat in the API layer).
    if len(df):
        df["lichess_url"] = df.apply(
            lambda r: chess_display.lichess_game_url(r.game_id, r.site) or "", axis=1)
    else:
        df["lichess_url"] = pd.Series(dtype=str)
    df["platform"] = df["site"].map(
        lambda s: "Chess.com" if s == chess_display.CHESSCOM_SITE_HEADER else "Lichess")
    return df.to_dict(orient="records")


@router.get("/api/games/explorer")
def games_explorer():
    return _game_explorer_cache.get(_compute_game_explorer_rows)


@router.get("/api/games/{game_id}")
def game_detail(game_id: str):
    sqlite_conn, _ = get_db_connections()
    try:
        header, moves = data.get_game_detail(sqlite_conn, game_id)
    except IndexError:
        # get_game_detail does header.iloc[0] on a query result --
        # IndexError on an unknown game_id. Streamlit never hits this
        # (navigation only ever passes a real row's id); an API client can
        # pass a stale/garbage id via URL, so this needs real handling.
        raise HTTPException(status_code=404, detail="Game not found")

    moves = moves.copy()
    moves["fen_after"] = [narrative.position_after_ply(moves, ply) for ply in moves["ply"]]
    win_prob = narrative.player_win_prob_series(moves)

    header_dict = header.to_dict()
    explorer_rows = _game_explorer_cache.get(_compute_game_explorer_rows)
    badge_row = next((r for r in explorer_rows if r["game_id"] == game_id), None)
    header_dict["lichess_url"] = badge_row["lichess_url"] if badge_row else ""
    for flag in ("is_comeback", "is_giant_killing", "is_brilliant_find",
                 "is_blunder_fest", "is_nail_biter"):
        header_dict[flag] = bool(badge_row[flag]) if badge_row else False

    return _json_safe({
        "header": header_dict,
        "moves": moves.to_dict(orient="records"),
        "win_prob": win_prob.to_dict(orient="records"),
    })


@router.get("/api/games/{game_id}/report")
def get_game_report(game_id: str):
    sqlite_conn, _ = get_db_connections()
    cached = data.get_cached_narrative(sqlite_conn, "game_report", game_id)
    if not cached:
        return {"report_text": None, "generated_at": None}
    report_text, generated_at = cached
    return {"report_text": report_text, "generated_at": generated_at}


@router.post("/api/games/{game_id}/report/generate")
def generate_game_report(game_id: str):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import game_report
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")

    sqlite_conn, _ = get_db_connections()
    try:
        header, moves = data.get_game_detail(sqlite_conn, game_id)
    except IndexError:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        game_report.generate_report(sqlite_conn, game_id, header, moves)
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")

    report_text, generated_at = data.get_cached_narrative(sqlite_conn, "game_report", game_id)
    return {"report_text": report_text, "generated_at": generated_at}


@router.get("/api/games/{game_id}/report/download.md")
def download_game_report_md(game_id: str):
    sqlite_conn, _ = get_db_connections()
    try:
        header, _ = data.get_game_detail(sqlite_conn, game_id)
    except IndexError:
        raise HTTPException(status_code=404, detail="Game not found")
    cached = data.get_cached_narrative(sqlite_conn, "game_report", game_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No report generated yet")
    report_text, _generated_at = cached

    safe_opp = (header.opponent_name or "game").replace(" ", "_")
    report_filename = f"chesswright_report_{safe_opp}_{header.utc_date}.md"
    return Response(
        content=report_text,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{report_filename}"'},
    )


@router.get("/api/games/{game_id}/report/download.html")
def download_game_report_html(game_id: str):
    sqlite_conn, _ = get_db_connections()
    try:
        header, _ = data.get_game_detail(sqlite_conn, game_id)
    except IndexError:
        raise HTTPException(status_code=404, detail="Game not found")
    cached = data.get_cached_narrative(sqlite_conn, "game_report", game_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No report generated yet")
    report_text, generated_at = cached

    safe_opp = (header.opponent_name or "game").replace(" ", "_")
    report_filename = f"chesswright_report_{safe_opp}_{header.utc_date}.md"
    html_filename = report_filename[:-len(".md")] + ".html"
    body_html = report_html.markdown_to_html(report_text)
    report_html_str = report_html.render_report_html(
        "game_report.html",
        title=f"Game Report — vs {header.opponent_name} ({header.utc_date})",
        opponent_name=header.opponent_name,
        utc_date=header.utc_date,
        result=header.outcome_for_player,
        color=header.player_color,
        opening=header.opening_family,
        time_control=header.time_control_category,
        generated_at=generated_at,
        body_html=body_html,
    )
    return Response(
        content=report_html_str,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{html_filename}"'},
    )


class AnalysePositionRequest(BaseModel):
    fen: str


def _decode_pv(pv_json: str | None) -> list[str]:
    return json.loads(pv_json) if pv_json else []


def _cached_analysis_result(cached: dict) -> dict:
    """data.get_position_analysis()'s dict already has best_move_from/to
    resolved and its own source label ("stored" from the moves table,
    "cached" from position_cache) -- just decode pv_json and rename to the
    endpoint's response shape."""
    return {
        "eval_cp": cached["eval_cp"],
        "eval_mate": cached["eval_mate"],
        "best_move_san": cached["best_move_san"],
        "best_move_from": cached["best_move_from"],
        "best_move_to": cached["best_move_to"],
        "pv": _decode_pv(cached["pv_json"]),
        "depth": cached["depth"],
        "source": cached["source"],
    }


def _fresh_analysis_result(fen: str, live_result, source: str) -> dict:
    """A LiveResult from lichess_cloud_eval.fetch_cloud_eval() or
    EngineService.analyse() -- unlike the cached-DB path, best_move_from/to
    aren't precomputed, so resolve them the same way
    data.get_position_analysis() does internally."""
    best_move_from, best_move_to = data.resolve_move_squares(fen, live_result.best_move_san)
    return {
        "eval_cp": live_result.eval_cp,
        "eval_mate": live_result.eval_mate,
        "best_move_san": live_result.best_move_san,
        "best_move_from": best_move_from,
        "best_move_to": best_move_to,
        "pv": _decode_pv(live_result.pv_json),
        "depth": live_result.depth,
        "source": source,
    }


@router.post("/api/analyse-position")
def analyse_position(body: AnalysePositionRequest):
    sqlite_conn, _ = get_db_connections()
    fen = body.fen

    cached = data.get_position_analysis(sqlite_conn, fen)
    if cached is not None:
        return {"status": "ok", "result": _cached_analysis_result(cached)}

    cfg = config.load_config().get("interactive_engine", {})
    if cfg.get("use_lichess_cloud_eval", True):
        cloud_result = lichess_cloud_eval.fetch_cloud_eval(fen)
        if cloud_result is not None:
            data.store_position_analysis(sqlite_conn, fen, cloud_result)
            return {"status": "ok",
                    "result": _fresh_analysis_result(fen, cloud_result, "lichess_cloud")}

    # Checked explicitly here (not just relying on EngineService.analyse()'s
    # own internal joblock guard) so batch_running can be reported as its
    # own status rather than collapsing into analysis_failed -- see the
    # Global Constraints note on this in the plan.
    lock_info = joblock.status()
    if lock_info is not None and lock_info.alive:
        return {"status": "batch_running", "result": None}

    # Only reached in direct response to this user-initiated request --
    # never called from a page-load path. See engine_status.py's own
    # get_engine_status_summary() docstring for why that matters.
    engine_svc = engine_status.get_engine_service()
    if engine_svc is None:
        return {"status": "no_engine", "result": None}

    live_result = engine_svc.analyse(fen)
    if live_result is None:
        return {"status": "analysis_failed", "result": None}

    data.store_position_analysis(sqlite_conn, fen, live_result)
    return {"status": "ok", "result": _fresh_analysis_result(fen, live_result, "live")}

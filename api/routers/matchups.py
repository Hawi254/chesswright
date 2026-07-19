"""GET/POST /api/matchups/* -- Rating & Form, Nemesis, per-opponent
profile/swindle-rate/narrative (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md). Reads,
but does not own, api.shared_data._points_ledger_cache --
/api/points/summary (api/routers/points.py, Task 5) owns the same cache
instance.
"""
from fastapi import APIRouter, HTTPException

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe, _narrative_response
import api.shared_data as shared_data

import claude_narrative
import data

router = APIRouter()

_PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]
_PIECE_NAME = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "K": "king"}

_matchups_static_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _matchups_static_cache.clear()


@router.get("/api/matchups/rating-form")
def matchups_rating_form():
    """One endpoint for all 6 argument-less Rating & Form queries -- always
    fetched together (one tab, no independent loading states), so one
    fetch + one _TTLCache entry beats six."""
    def compute():
        _, duck_conn = get_db_connections()
        reason_df, piece_df, mate_df = data.get_giant_killing_collapse_causes(duck_conn)
        piece_records = piece_df.to_dict(orient="records")
        order = {p: i for i, p in enumerate(_PIECE_ORDER)}
        piece_records.sort(key=lambda r: order.get(r["hung_piece"], len(_PIECE_ORDER)))
        for r in piece_records:
            r["piece_name"] = _PIECE_NAME.get(r["hung_piece"], r["hung_piece"]).title()
        # reindex(columns=...): the pivot's columns come from whatever
        # player_color values actually appear in the data -- on a small/
        # fresh DB that can be only one color (or, if player_color is ever
        # NULL, a NaN-named column that can't be JSON-serialized as a key
        # at all) -- reindexing guarantees both "black" and "white" keys
        # every time, matching the frontend's ColorPerformanceRow type.
        color_perf = data.get_color_performance_by_rating(duck_conn).reindex(columns=["black", "white"]).reset_index()
        # _json_safe: color_performance_by_rating's pivot.reindex(["underdog",
        # "even", "favorite"]) leaves an all-NaN row for any bucket with zero
        # games (routine on a small/fresh database), and
        # giant_killing_rate_trend's pct_upset/pct_collapse are NaN by design
        # whenever a quarter's denominator is 0 (see that function's own
        # docstring) -- both would otherwise 500 under starlette's
        # allow_nan=False, the same failure mode _json_safe already guards
        # against for game_detail and openings_table.
        return _json_safe({
            "win_rate_by_rating_diff": data.get_win_rate_by_rating_diff(duck_conn).to_dict(orient="records"),
            "color_performance_by_rating": color_perf.to_dict(orient="records"),
            "giant_killing_counts": data.get_giant_killing_counts(duck_conn),
            "collapse_causes": {
                "reason": reason_df.to_dict(orient="records"),
                "piece": piece_records,
                "mate": mate_df.to_dict(orient="records"),
            },
            "giant_killing_rate_trend": data.get_giant_killing_rate_trend(duck_conn).to_dict(orient="records"),
            "comeback_collapse": data.get_comeback_collapse_counts(duck_conn),
        })
    return _matchups_static_cache.get(compute)


@router.get("/api/matchups/nemesis")
def matchups_nemesis(min_games: int | None = None):
    _, duck_conn = get_db_connections()
    return data.get_nemesis_opponents(duck_conn, min_games=min_games).to_dict(orient="records")


@router.get("/api/matchups/opponent-profile")
def opponent_profile(opponent_name: str):
    _, duck_conn = get_db_connections()
    profile = data.get_opponent_profile(duck_conn, opponent_name)
    # _json_safe: acpl in "openings" and "clock" is NaN whenever the LEFT
    # JOIN finds no analyzed moves for that opening/bucket (matchups_view.py's
    # own comment on this exact NaN -- there it's a display-string fix,
    # here it would 500 the whole response without _json_safe).
    return _json_safe({
        "n_games": profile["n_games"],
        "openings": profile["openings"].to_dict(orient="records"),
        "position": profile["position"].to_dict(orient="records"),
        "castling": profile["castling"].to_dict(orient="records"),
        "action_side": profile["action_side"].to_dict(orient="records"),
        "clock": profile["clock"].to_dict(orient="records"),
    })


@router.get("/api/matchups/opponent-swindle-rate")
def opponent_swindle_rate(opponent_name: str):
    _, duck_conn = get_db_connections()
    ledger = shared_data._points_ledger_cache.get(
        lambda: data.classify_points_ledger(data.get_points_ledger(duck_conn)))
    return data.get_opponent_swindle_rate(ledger, opponent_name)


@router.get("/api/matchups/opponent-narrative")
def get_opponent_narrative(opponent_name: str):
    sqlite_conn, _ = get_db_connections()
    return _narrative_response(data.get_cached_narrative(sqlite_conn, "opponent", opponent_name))


@router.post("/api/matchups/opponent-narrative/generate")
def generate_opponent_narrative(opponent_name: str):
    sqlite_conn, duck_conn = get_db_connections()
    nem_rows = data.get_nemesis_opponents(duck_conn, min_games=None)
    row = nem_rows.loc[nem_rows.opponent_name == opponent_name]
    if row.empty:
        raise HTTPException(status_code=404, detail="Unknown opponent")
    stats = shared_data.get_headline_stats_cached()
    try:
        response_text = claude_narrative.generate_opponent_commentary(
            row.iloc[0], stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "opponent", opponent_name, response_text, claude_narrative.MODEL)
    return {"narrative": response_text}

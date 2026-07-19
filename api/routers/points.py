"""GET /api/points/summary -- "Where Your Points Go" (moved from
api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md; router
added per that plan's Deviation #1 -- this page shipped 2026-07-16 and the
spec's own file-layout list predates it). Reads, but does not own,
api.shared_data._points_ledger_cache -- /api/matchups/opponent-swindle-rate
(api/routers/matchups.py, Task 9) reads the same cache instance.
"""
import pandas as pd
from fastapi import APIRouter

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe
import api.shared_data as shared_data

import chess_display
import data

router = APIRouter()

_PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]
_PIECE_NAME = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "K": "king"}
_VALID_TIME_CONTROLS = ("bullet", "blitz", "rapid", "classical")

_points_summary_cache = {tc: TTLCache(60) for tc in (None,) + _VALID_TIME_CONTROLS}


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    for _cache in _points_summary_cache.values():
        _cache.clear()


def _empty_points_response(tc_options, analyzed_games):
    return {
        "tc_options": tc_options,
        "n_games": 0,
        "actual_pct": 0.0,
        "leaked_points": 0.0,
        "ceiling_pct": 0.0,
        "buckets": [],
        "monthly": [],
        "conversion_breakdown": {"adv_band": [], "conv_phase": [], "conv_clock": []},
        "causes": {"reason": [], "piece": [], "mate": []},
        "costliest_games": [],
        "analyzed_games": analyzed_games,
    }


@router.get("/api/points/summary")
def points_summary(time_control: str | None = None):
    tc = time_control if time_control in _VALID_TIME_CONTROLS else None

    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        classified = shared_data._points_ledger_cache.get(
            lambda: data.classify_points_ledger(data.get_points_ledger(duck_conn)))
        tc_options = sorted(classified.time_control_category.dropna().unique().tolist())

        if classified.empty:
            stats = shared_data.get_headline_stats_cached()
            return _json_safe(_empty_points_response(tc_options, stats["analyzed_games"]))

        view = classified if tc is None else classified[classified.time_control_category == tc]
        if view.empty:
            return _json_safe(_empty_points_response(tc_options, None))

        summary = data.summarize_buckets(view)
        n = len(view)
        actual = view.points.sum()
        leaked = view.leaked.sum()

        monthly = data.monthly_points(view)
        if not monthly.empty:
            # monthly_points' own docstring: raw "YYYY.MM" period strings look
            # numeric to Plotly and get misread as a fractional-year axis --
            # the Streamlit page fixed this by parsing to a real datetime
            # before charting; an unambiguous ISO string survives the same
            # trip through JSON and into react-plotly.js's date x-axis.
            monthly = monthly.assign(month=monthly.month.dt.strftime("%Y-%m-%d"))

        reason_df, piece_df, mate_df = data.get_failed_conversion_causes(duck_conn, view)
        piece_order = {p: i for i, p in enumerate(_PIECE_ORDER)}
        piece_records = sorted(
            piece_df.to_dict(orient="records"),
            key=lambda r: piece_order.get(r["hung_piece"], len(_PIECE_ORDER)))
        piece_out = [
            {"label": _PIECE_NAME.get(r["hung_piece"], r["hung_piece"]).title(), "n": r["n"], "pct": r["pct"]}
            for r in piece_records
        ]
        mate_out = [
            {"label": r["bucket"], "n": r["n"], "pct": r["pct"]}
            for r in mate_df.to_dict(orient="records")
        ]

        worst = view[view.bucket != "none"].nlargest(15, "leaked").copy()
        worst["best_chance"] = worst.peak_wp.where(worst.bucket != "missed_swindle", worst.post_lost_peak_wp)
        # .apply(axis=1) on a 0-row frame returns a DataFrame, not a Series --
        # found live before (see pandas_empty_df_apply_axis1_gotcha in
        # project memory) -- guard it explicitly rather than relying on
        # nlargest(15, ...) never producing an empty frame.
        if worst.empty:
            worst["url"] = pd.Series(dtype="object")
        else:
            worst["url"] = worst.apply(lambda r: chess_display.lichess_game_url(r.game_id, r.site), axis=1)

        return _json_safe({
            "tc_options": tc_options,
            "n_games": n,
            "actual_pct": 100.0 * actual / n,
            "leaked_points": leaked,
            "ceiling_pct": 100.0 * (actual + leaked) / n,
            "buckets": summary.to_dict(orient="records"),
            "monthly": monthly.to_dict(orient="records"),
            "conversion_breakdown": {
                "adv_band": data.conversion_breakdown(view, "adv_band").to_dict(orient="records"),
                "conv_phase": data.conversion_breakdown(view, "conv_phase").to_dict(orient="records"),
                "conv_clock": data.conversion_breakdown(view, "conv_clock").to_dict(orient="records"),
            },
            "causes": {
                "reason": reason_df.to_dict(orient="records"),
                "piece": piece_out,
                "mate": mate_out,
            },
            "costliest_games": worst[["game_id", "utc_date", "opponent_name", "outcome_for_player",
                                      "bucket", "best_chance", "leaked", "url"]].to_dict(orient="records"),
            "analyzed_games": None,
        })
    return _points_summary_cache[tc].get(compute)

"""GET /api/patterns/* -- Clock & Time, Turning Points, Piece Handling,
Positions, Game Context, Comparisons, Playing Sessions, and the Patterns
page's cross-tab summary strip (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
from typing import Literal

import pandas as pd
from fastapi import APIRouter

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe

import chess_display
import data
from confidence import confidence_tier
from connections import get_config
from data.insights import BUCKET_MOVES_THRESHOLDS

router = APIRouter()

_patterns_clock_time_cache = TTLCache(60)
_patterns_turning_points_cache = TTLCache(60)
_patterns_pieces_cache = {"phase": TTLCache(60), "sharpness": TTLCache(60)}
_patterns_positions_cache = {
    (st, gr): TTLCache(60)
    for st in ("endgame", "middlegame") for gr in (False, True)
}
_patterns_game_context_cache = TTLCache(60)
_patterns_comparisons_cache = TTLCache(60)
_patterns_sessions_cache = TTLCache(60)
_patterns_summary_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _patterns_clock_time_cache.clear()
    _patterns_turning_points_cache.clear()
    for _cache in _patterns_pieces_cache.values():
        _cache.clear()
    for _cache in _patterns_positions_cache.values():
        _cache.clear()
    _patterns_game_context_cache.clear()
    _patterns_comparisons_cache.clear()
    _patterns_sessions_cache.clear()
    _patterns_summary_cache.clear()


@router.get("/api/patterns/clock-time")
def patterns_clock_time():
    """One endpoint for all 5 argument-less Clock & Time queries -- always
    fetched together (one tab, no independent loading states), same
    reasoning as /api/matchups/rating-form."""
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        result_df, n_analyzed, n_total_in_scope = data.get_instant_move_accuracy_by_legal_replies(duck_conn)
        return _json_safe({
            "blunder_rate_by_time_pressure":
                data.get_blunder_rate_by_time_pressure(duck_conn).to_dict(orient="records"),
            "acpl_by_time_control":
                data.get_acpl_by_time_control(sqlite_conn).to_dict(orient="records"),
            "thinking_time_blunder_correlation":
                data.get_thinking_time_blunder_correlation(duck_conn).to_dict(orient="records"),
            "instant_move_rate_by_phase":
                data.get_instant_move_rate_by_phase(duck_conn).to_dict(orient="records"),
            "instant_move_accuracy": {
                "rows": result_df.to_dict(orient="records"),
                "n_analyzed": n_analyzed,
                "n_total_in_scope": n_total_in_scope,
            },
        })
    return _patterns_clock_time_cache.get(compute)


def _clock_time_tendency_card(duck_conn):
    """Picks the headline blunder-rate-by-clock-pressure stat out of
    get_blunder_rate_by_time_pressure's existing result -- the same
    worst-vs-best-bucket extraction dashboard/data/insights.py's
    _time_pressure() Finding uses, trimmed to the TendencyCard shape (no
    severity/confidence chip -- see the page design spec's decision on
    TendencyCard vs InsightCard). Returns None if fewer than 2 buckets
    clear the confidence gate, mirroring _time_pressure()'s own None
    return for "not enough data to say anything.\""""
    df = data.get_blunder_rate_by_time_pressure(duck_conn)
    qualifying = df[df.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(qualifying) < 2:
        return None
    worst = qualifying.loc[qualifying.blunder_rate.idxmax()]
    best = qualifying.loc[qualifying.blunder_rate.idxmin()]
    return {
        "tab_id": "clock-time",
        "label": "Clock & Time",
        "headline": f"Blunder rate peaks at {worst.blunder_rate:.1f}% with \"{worst.bucket}\" clock left",
        "detail": f"vs. {best.blunder_rate:.1f}% with \"{best.bucket}\" clock left",
    }


@router.get("/api/patterns/turning-points")
def patterns_turning_points():
    def compute():
        _, duck_conn = get_db_connections()
        return _json_safe(data.get_decisive_moments_breakdown(duck_conn))
    return _patterns_turning_points_cache.get(compute)


def _turning_points_tendency_card(duck_conn):
    """Median decisive-move number + most common phase across every
    contested loss -- no per-bucket confidence gate needed (this
    aggregates to one median/mode across all losses, unlike Clock &
    Time's per-bucket rates). Returns None only when there are zero
    contested losses."""
    breakdown = data.get_decisive_moments_breakdown(duck_conn)
    if breakdown["n_losses"] == 0:
        return None
    return {
        "tab_id": "turning-points",
        "label": "Turning Points",
        "headline": f"Losses typically turn at move {breakdown['median_move']} "
                    f"({breakdown['most_common_phase']})",
        "detail": f"Based on {breakdown['n_losses']} losses with a contested position",
    }


@router.get("/api/patterns/pieces")
def patterns_pieces(view_by: Literal["phase", "sharpness"] = "phase"):
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        piece_df = data.get_piece_movement_patterns(duck_conn)
        if view_by == "sharpness":
            view_df = data.get_piece_blunder_by_sharpness(duck_conn)
        else:
            view_df = data.get_piece_blunder_by_phase(sqlite_conn)
        bishop_df = data.get_bishop_square_color_performance(duck_conn)
        backrank_df = data.get_rook_king_backrank_performance(duck_conn)
        blunder_pivot, n_moves_pivot, n_analyzed, n_total_in_scope = data.get_square_blunder_heatmap(duck_conn)

        cells = []
        if blunder_pivot is not None:
            long_blunder = (blunder_pivot.reset_index()
                             .melt(id_vars="rank", var_name="file", value_name="blunder_rate")
                             .dropna(subset=["blunder_rate"]))
            long_n_moves = (n_moves_pivot.reset_index()
                             .melt(id_vars="rank", var_name="file", value_name="n_moves")
                             .dropna(subset=["n_moves"]))
            merged = long_blunder.merge(long_n_moves, on=["rank", "file"])
            cells = [
                {"file": r.file, "rank": int(r.rank), "blunder_rate": r.blunder_rate, "n_moves": int(r.n_moves)}
                for r in merged.itertuples()
            ]

        win_df, acpl_df = data.get_castling_performance(duck_conn)

        return _json_safe({
            "piece_movement": piece_df.to_dict(orient="records"),
            "piece_by_view": view_df.to_dict(orient="records"),
            "bishop_square_color": bishop_df.to_dict(orient="records"),
            "rook_king_backrank": backrank_df.to_dict(orient="records"),
            "square_heatmap": {
                "cells": cells,
                "n_analyzed": n_analyzed,
                "n_total_in_scope": n_total_in_scope,
            },
            "motif_backfill_needed": data.motif_backfill_needed(duck_conn),
            "castling": {
                "win": win_df.to_dict(orient="records"),
                "acpl": acpl_df.to_dict(orient="records"),
            },
        })
    return _patterns_pieces_cache[view_by].get(compute)


def _piece_handling_tendency_card(duck_conn):
    """Worst blunder-rate piece from get_piece_movement_patterns vs. the
    all-piece mean, same worst-vs-baseline extraction shape as
    _clock_time_tendency_card. Gated on the same confidence_tier check;
    returns None if fewer than 2 pieces clear the confidence gate."""
    df = data.get_piece_movement_patterns(duck_conn)
    qualifying = df[df.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(qualifying) < 2:
        return None
    worst = qualifying.loc[qualifying.blunder_rate.idxmax()]
    mean_blunder_rate = qualifying.blunder_rate.mean()
    return {
        "tab_id": "piece-handling",
        "label": "Piece Handling",
        "headline": f"{worst.piece_name} blunders most often, at {worst.blunder_rate:.1f}%",
        "detail": f"vs. {mean_blunder_rate:.1f}% average across all pieces",
    }


@router.get("/api/patterns/positions")
def patterns_positions(structure_type: Literal["endgame", "middlegame"] = "endgame",
                        grouped: bool = False):
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        sharpness_df = data.get_sharpness_blunder_correlation(duck_conn)

        if grouped:
            # data.patterns.* (submodule attribute, not data.*) deliberately
            # here -- get_material_structure_bucket_table isn't re-exported
            # through dashboard/data/__init__.py's flat namespace (confirmed
            # by grep). Works because `import data` already imports the
            # patterns submodule at package-init time.
            structure_df = data.patterns.get_material_structure_bucket_table(
                sqlite_conn, structure_type=structure_type)
            label_header, label_col = "Category", "bucket"
        else:
            structure_df = data.get_material_structure_table(
                sqlite_conn, structure_type=structure_type)
            label_header, label_col = "Position Type", "material_sig"

        n_unanalyzed = int((structure_df.n_analyzed == 0).sum())
        structure_display = structure_df.rename(columns={label_col: "label"})
        if not grouped:
            # Display-layer only, same reasoning as patterns_view.py's own
            # cached_material_structure_table caller -- the raw
            # "Q1R1B1P6vQ1R1B1P6" encoding is accurate but not meant for a
            # reader. A unified "label" key regardless of grouped, unlike
            # Streamlit's label_col/label_header switch (see design spec
            # decision 2) -- the frontend table never branches on which
            # column holds the row label.
            structure_display["label"] = structure_display["label"].apply(
                chess_display.material_sig_str)

        bishop_df = data.get_bishop_color_ending_performance(duck_conn, sqlite_conn)
        pc = data.get_position_character_performance(duck_conn)
        gs = data.get_game_side_performance(duck_conn)

        return _json_safe({
            "sharpness": sharpness_df.to_dict(orient="records"),
            "material_structure": {
                "rows": structure_display.to_dict(orient="records"),
                "label_header": label_header,
                "n_unanalyzed": n_unanalyzed,
            },
            "bishop_endings": bishop_df.to_dict(orient="records"),
            "position_character": {
                "bucket_win": pc["bucket_win"].to_dict(orient="records"),
                "bucket_acpl": pc["bucket_acpl"].to_dict(orient="records"),
                "symmetric_win": pc["symmetric_win"].to_dict(orient="records"),
                "symmetric_acpl": pc["symmetric_acpl"].to_dict(orient="records"),
                "central_tension_pct": pc["central_tension_pct"],
                "n_classified": pc["n_classified"],
                "n_total_games": pc["n_total_games"],
            },
            "game_side": {
                "castling_win": gs["castling_win"].to_dict(orient="records"),
                "castling_acpl": gs["castling_acpl"].to_dict(orient="records"),
                "action_win": gs["action_win"].to_dict(orient="records"),
                "action_acpl": gs["action_acpl"].to_dict(orient="records"),
            },
        })
    return _patterns_positions_cache[(structure_type, grouped)].get(compute)


def _positions_tendency_card(duck_conn):
    """Same worst-vs-best-bucket extraction as _clock_time_tendency_card,
    over get_sharpness_blunder_correlation's [bucket, n_moves, acpl,
    blunder_rate] result (identical shape to time-pressure's) -- a
    near-literal copy with a different data call and label text. Returns
    None if fewer than 2 buckets clear the confidence gate."""
    df = data.get_sharpness_blunder_correlation(duck_conn)
    qualifying = df[df.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(qualifying) < 2:
        return None
    worst = qualifying.loc[qualifying.blunder_rate.idxmax()]
    best = qualifying.loc[qualifying.blunder_rate.idxmin()]
    return {
        "tab_id": "positions",
        "label": "Positions",
        "headline": f"Blunder rate peaks at {worst.blunder_rate:.1f}% in \"{worst.bucket}\" positions",
        "detail": f"vs. {best.blunder_rate:.1f}% in \"{best.bucket}\" positions",
    }


@router.get("/api/patterns/game-context")
def patterns_game_context():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        phase_df = data.get_phase_accuracy(sqlite_conn)
        win_pivot, rating_pivot = data.get_day_hour_heatmap(duck_conn)
        cfg = get_config()
        utc_offset_hours = cfg["analytics"]["utc_offset_hours"]

        # day_of_week is stored 0=Monday..6=Sunday (migrations/0001_init.sql)
        # -- same day_labels map _render_tab_rhythm applies for display.
        day_labels = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        win_long = (win_pivot.reset_index()
                    .melt(id_vars="day_of_week", var_name="hour_local", value_name="win_pct")
                    .dropna(subset=["win_pct"]))
        rating_long = (rating_pivot.reset_index()
                       .melt(id_vars="day_of_week", var_name="hour_local", value_name="rating_diff")
                       .dropna(subset=["rating_diff"]))
        merged = win_long.merge(rating_long, on=["day_of_week", "hour_local"], how="left")
        merged["day"] = merged["day_of_week"].map(day_labels)
        # Pre-formatted signed-integer display strings, not raw floats --
        # same convention _render_tab_rhythm's own rating_df.map already
        # uses; charts.heatmap's hoverExtra applies no numeric format spec.
        merged["rating_diff_display"] = merged["rating_diff"].apply(
            lambda v: "--" if pd.isna(v) else f"{v:+.0f}")

        cells = [
            {"day": r.day, "hour_local": int(r.hour_local), "win_pct": r.win_pct,
             "rating_diff_display": r.rating_diff_display}
            for r in merged.itertuples()
        ]

        return _json_safe({
            "phase_accuracy": phase_df.to_dict(orient="records"),
            "day_hour_heatmap": {
                "cells": cells,
                "utc_offset_hours": utc_offset_hours,
            },
        })
    return _patterns_game_context_cache.get(compute)


def _game_context_tendency_card(duck_conn):
    """Worst-vs-best *phase* by acpl (the phase-accuracy panel's own axis,
    not blunder rate) over get_phase_accuracy's 3-row result. No
    confidence-tier gate -- only 3 phases, every phase with any analyzed
    moves qualifies. Returns None only when get_phase_accuracy returns an
    empty frame (zero analyzed player moves total). Takes duck_conn only
    to match every sibling *_tendency_card's call signature from
    patterns_summary() -- get_phase_accuracy itself needs sqlite_conn, so
    this fetches its own via get_db_connections() (cheap: it returns the
    same process-wide cached connections object every call, same as every
    other endpoint in this file already does) rather than threading a
    second, differently-typed parameter through patterns_summary()."""
    sqlite_conn, _ = get_db_connections()
    df = data.get_phase_accuracy(sqlite_conn)
    if df.empty:
        return None
    worst = df.loc[df.acpl.idxmax()]
    best = df.loc[df.acpl.idxmin()]
    return {
        "tab_id": "game-context",
        "label": "Game Context",
        "headline": f"ACPL is highest in the {worst.phase}, at {worst.acpl:.0f}",
        "detail": f"vs. {best.acpl:.0f} in the {best.phase}",
    }


@router.get("/api/patterns/comparisons")
def patterns_comparisons():
    def compute():
        _, duck_conn = get_db_connections()
        win_df, acpl_df = data.get_favorite_underdog_performance(duck_conn)
        return _json_safe({
            "favorite_underdog": {
                "win": win_df.to_dict(orient="records"),
                "acpl": acpl_df.to_dict(orient="records"),
            },
            "clock_pressure_by_rating_bucket":
                data.get_clock_pressure_by_rating_bucket(duck_conn).to_dict(orient="records"),
            "openings_by_rating_bucket":
                data.get_openings_by_rating_bucket(duck_conn).to_dict(orient="records"),
            "clock_pressure_by_outcome":
                data.get_clock_pressure_by_outcome(duck_conn).to_dict(orient="records"),
            "clock_pressure_by_color":
                data.get_clock_pressure_by_color(duck_conn).to_dict(orient="records"),
            "clock_pressure_by_opening":
                data.get_clock_pressure_by_opening(duck_conn).to_dict(orient="records"),
        })
    return _patterns_comparisons_cache.get(compute)


def _comparisons_tendency_card(duck_conn):
    """Underdog-vs-favorite win-rate gap, from the tab's own headline
    panel (get_favorite_underdog_performance's win_df) -- the single most
    legible number this tab has, since every other panel is itself a
    comparison rather than a single worst-vs-best bucket. Returns None if
    either the underdog or favorite bucket has zero games."""
    win_df, _ = data.get_favorite_underdog_performance(duck_conn)
    underdog = win_df[win_df.bucket == "underdog"]
    favorite = win_df[win_df.bucket == "favorite"]
    if underdog.empty or favorite.empty:
        return None
    u, f = underdog.iloc[0], favorite.iloc[0]
    return {
        "tab_id": "comparisons",
        "label": "Comparisons",
        "headline": f"Win rate as underdog: {u.win_pct:.1f}%",
        "detail": f"vs. {f.win_pct:.1f}% as favorite",
    }


@router.get("/api/patterns/sessions")
def patterns_sessions():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        return _json_safe({
            "session_rollup": data.get_session_rollup(sqlite_conn).to_dict(orient="records"),
            "prior_outcome": data.get_prior_outcome_performance(sqlite_conn).to_dict(orient="records"),
            "session_position": data.get_session_position_performance(sqlite_conn).to_dict(orient="records"),
            "event_type": data.get_event_type_performance(duck_conn).to_dict(orient="records"),
            "event_name_breakdown": data.get_event_name_breakdown(duck_conn).to_dict(orient="records"),
        })
    return _patterns_sessions_cache.get(compute)


def _sessions_tendency_card(duck_conn):
    """Worst-vs-best ACPL bucket from get_prior_outcome_performance --
    same worst-vs-best-bucket extraction shape as _clock_time_tendency_
    card, gated the same way (confidence_tier over n_moves). Uses
    get_db_connections() for sqlite_conn directly, same reasoning
    _game_context_tendency_card already documents for this pattern.
    Returns None if fewer than 2 buckets clear the confidence gate."""
    sqlite_conn, _ = get_db_connections()
    df = data.get_prior_outcome_performance(sqlite_conn)
    qualifying = df[df.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(qualifying) < 2:
        return None
    worst = qualifying.loc[qualifying.acpl.idxmax()]
    best = qualifying.loc[qualifying.acpl.idxmin()]
    return {
        "tab_id": "sessions",
        "label": "Playing Sessions",
        "headline": f"ACPL is highest {worst.bucket}, at {worst.acpl:.0f}",
        "detail": f"vs. {best.acpl:.0f} {best.bucket}",
    }


@router.get("/api/patterns/summary")
def patterns_summary():
    """One headline stat per built Patterns tab -- grows by one list entry
    per slice as the 7-slice roadmap lands. Picks the lead number out of
    each tab's own existing result, no new queries -- same spirit as
    /api/overview/career-highlight."""
    def compute():
        _, duck_conn = get_db_connections()
        cards = [
            _clock_time_tendency_card(duck_conn),
            _turning_points_tendency_card(duck_conn),
            _piece_handling_tendency_card(duck_conn),
            _positions_tendency_card(duck_conn),
            _game_context_tendency_card(duck_conn),
            _comparisons_tendency_card(duck_conn),
            _sessions_tendency_card(duck_conn),
        ]
        return [c for c in cards if c is not None]
    return _patterns_summary_cache.get(compute)

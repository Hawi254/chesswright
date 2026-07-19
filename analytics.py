#!/usr/bin/env python3
"""
Phase 4a: Core rollups -- ACPL & blunder rate by context.

Pure read-only SQL aggregation over already-stored moves/games columns.
No new migration, nothing written back -- re-running this after more
worker.py batches complete just reflects more data. Every section states
its own sample size so a stat from a handful of analyzed games is never
mistaken for one covering the whole real dataset.

Usage:
    python3 analytics.py                       # full report
    python3 analytics.py --section opening      # one section only

Split (largest-file modularization, 2026-07-17) into four sibling
modules -- analytics_reports.py (every report_by_*/acpl_and_blunder_rate/
classification_breakdown/fmt_row function), analytics_session.py
(compute_session_context/ensure_session_ctx), analytics_structure.py
(compute_structure_context/ensure_structure_ctx/player_relative_sig),
analytics_position_caches.py (the three cache-rebuild ensure_* functions,
plus _open_write_connection -- see analytics_position_caches.py's own
docstring for why that one function moved here rather than staying in
this file as originally scoped) -- this file keeps only run()/main() and
re-exports everything above so every existing import path
(`analytics.ensure_structure_ctx`, `from analytics import
acpl_and_blunder_rate`, etc.) keeps working unchanged.
"""
import argparse

from db import get_connection
from config import load_config, pick

from analytics_reports import (
    BASE_FILTER, acpl_and_blunder_rate, classification_breakdown, fmt_row,
    report_overall, report_by_outcome, report_by_time_control, report_by_opening,
    report_by_rating_bucket, report_by_hour_bucket, report_by_day_of_week,
    SESSION_JOIN, report_by_session_position, report_by_prior_outcome,
    report_by_losing_streak, SESSION_SECTIONS, fmt_structure_row,
    report_by_middlegame_structure, report_by_endgame_structure, STRUCTURE_SECTIONS,
)
from analytics_session import compute_session_context, ensure_session_ctx
from analytics_structure import compute_structure_context, ensure_structure_ctx, player_relative_sig
from analytics_position_caches import (
    _open_write_connection, ensure_opening_position_stats,
    ensure_repeated_positions_cache, ensure_repertoire_holes_cache,
)


def run(db_path, cfg, section):
    conn = get_connection(db_path)
    min_sample_size = cfg["analytics"]["min_sample_size"]

    if section is None or section in SESSION_SECTIONS:
        ensure_session_ctx(conn, cfg["analytics"]["session_gap_minutes"])
    if section is None or section in STRUCTURE_SECTIONS:
        ensure_structure_ctx(conn, cfg)

    if section is None or section == "overall":
        report_overall(conn, min_sample_size)
    if section is None or section == "outcome":
        report_by_outcome(conn, min_sample_size)
    if section is None or section == "time_control":
        report_by_time_control(conn, min_sample_size)
    if section is None or section == "opening":
        report_by_opening(conn, min_sample_size,
                           cfg["analytics"]["min_games_per_group"],
                           cfg["analytics"]["top_n_openings"])
    if section is None or section == "rating":
        report_by_rating_bucket(conn, min_sample_size, cfg["analytics"]["rating_diff_buckets"])
    if section is None or section == "hour":
        report_by_hour_bucket(conn, min_sample_size, cfg["analytics"]["hour_buckets"],
                               cfg["analytics"]["utc_offset_hours"])
    if section is None or section == "day":
        report_by_day_of_week(conn, min_sample_size)
    if section is None or section == "session_position":
        report_by_session_position(conn, min_sample_size, cfg["analytics"]["session_position_cap"])
    if section is None or section == "prior_outcome":
        report_by_prior_outcome(conn, min_sample_size)
    if section is None or section == "losing_streak":
        report_by_losing_streak(conn, min_sample_size, cfg["analytics"]["losing_streak_cap"])
    if section is None or section == "middlegame_structure":
        report_by_middlegame_structure(conn, min_sample_size,
                                        cfg["analytics"]["structure_min_games_per_group"],
                                        cfg["analytics"]["structure_top_n"],
                                        cfg["analytics"]["middlegame_ply"])
    if section is None or section == "endgame_structure":
        report_by_endgame_structure(conn, min_sample_size,
                                     cfg["analytics"]["structure_min_games_per_group"],
                                     cfg["analytics"]["structure_top_n"])

    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--section", choices=["overall", "outcome", "time_control", "opening", "rating", "hour", "day",
                                           "session_position", "prior_outcome", "losing_streak",
                                           "middlegame_structure", "endgame_structure"],
                     default=None, help="Print just one section (default: full report)")
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])

    run(db_path, cfg, args.section)

"""Phase 6 Career Dashboard -- data layer. One function per panel, each
returning a pandas DataFrame (or a small dict for headline stats).

Split into one module per Career page (Phase 9.10 maintainability pass,
2026-06-23) -- the original single data.py grew to 1005 lines / ~39
functions as features were added across Phases 6-9, making it hard to
find "the openings query" among unrelated castling/rating/narrative
queries. This __init__.py re-exports every function/constant at the
package's top level so every existing call site (`import data;
data.get_whatever(...)`) keeps working without any changes -- only this
package's internal layout changed, not its public surface.

Functions take already-open connections (sqlite_conn / duck_conn), not a
db_path -- deliberate, after measuring a real cold-start cost: passing
db_path and opening a fresh connection per call meant ensure_structure_ctx/
ensure_session_ctx's "only build once per connection" check never paid
off (every call got a brand-new connection with no temp table yet), so
4 separate functions each independently re-scanned the full ~2M-row
moves table. Callers (app.py) open ONE sqlite connection and ONE DuckDB
connection per server session (via st.cache_resource) and pass them in --
this is what makes the existing ensure_*_ctx caching actually work.

Reuses analytics.py's functions directly wherever they already return
values (acpl_and_blunder_rate, compute_session_context,
compute_structure_context) rather than re-deriving that logic. For
hypotheses that originated in analysis/*.py scripts (which mostly print
rather than return), this module writes its own small DuckDB queries --
restating the same threshold CONSTANTS (not logic) those scripts use,
each with a comment pointing at the source of truth.
"""
from ._shared import (
    TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS,
    GIANT_KILLING_UPSET_THRESHOLD, GIANT_KILLING_COLLAPSE_THRESHOLD,
    COMEBACK_WP_THRESHOLD, COLLAPSE_WP_THRESHOLD,
    get_cached_narrative, save_narrative, get_headline_stats,
)
from .overview import (
    get_rating_trajectory, get_acpl_trajectory, get_win_rate_by_color,
    get_progress_by_month,
)
from .openings import (
    INITIAL_FEN, FLIP_SCAN_MIN_TOTAL_GAMES,
    get_openings_table, get_most_repeated_positions, get_opening_ply_accuracy,
    get_repertoire_holes, get_position_fen, get_position_analysis,
    store_position_analysis, get_opening_moves_from_fen,
    get_opening_moves_by_year, get_player_move_year_stats,
    compute_dominant_move_flips, summarize_position_timeline,
    get_path_to_position, resolve_move_squares,
)
from .patterns import (
    SHARPNESS_BUCKETS, PIECE_ORDER, PIECE_NAME,
    get_blunder_rate_by_time_pressure, get_acpl_by_time_control,
    get_phase_accuracy, get_prior_outcome_performance,
    get_session_position_performance, get_day_hour_heatmap,
    get_material_structure_table, get_bishop_color_ending_performance, get_piece_movement_patterns,
    get_piece_blunder_by_phase, get_piece_blunder_by_sharpness,
    get_bishop_square_color_performance, get_rook_king_backrank_performance,
    get_castling_performance, get_sharpness_blunder_correlation,
    get_thinking_time_blunder_correlation, get_decisive_moments,
    get_instant_move_rate_by_phase, get_instant_move_accuracy_by_legal_replies,
    get_position_character_performance, get_game_side_performance,
    get_square_blunder_heatmap,
    get_favorite_underdog_performance, get_clock_pressure_by_rating_bucket,
    get_clock_pressure_by_outcome, get_clock_pressure_by_color, get_clock_pressure_by_opening,
    get_openings_by_rating_bucket, get_session_rollup,
    get_event_type_performance, get_event_name_breakdown,
)
from .matchups import (
    get_win_rate_by_rating_diff, get_comeback_collapse_counts,
    get_color_performance_by_rating, get_giant_killing_counts,
    get_nemesis_opponents, get_giant_killing_collapse_causes,
    get_giant_killing_rate_trend, get_opponent_profile, get_opponent_swindle_rate,
)
from .game_endings import (
    get_game_end_type_breakdown, get_endgame_type_performance, get_resignation_loss_causes,
    get_resignation_time_pressure_trend, get_time_forfeit_loss_breakdown,
)
from .tactical import (
    RIM_SQL,
    get_puzzle_sequences, get_brilliant_candidates, get_best_move_streaks,
    get_blown_mates, get_knight_rim_performance, get_hallucination_blunders,
    get_hallucination_context, get_motif_breakdown, motif_backfill_needed,
)
from .game_explorer import (
    BLUNDER_FEST_THRESHOLD, BRILLIANT_FIND_THRESHOLD, NAIL_BITER_THRESHOLD,
    get_game_badges, get_game_explorer_table, get_game_detail,
)
from .insights import get_career_findings
from .points import (
    get_failed_conversion_causes,
    WINNING_WP, LOST_WP, SWINDLE_CHANCE_WP, EVEN_WP, HOLD_EVEN_MIN_MOVE,
    CONVERSION_BANDS, BUCKET_LABEL,
    get_points_ledger, classify_points_ledger, summarize_buckets,
    monthly_points, conversion_breakdown,
)
from .evolution import (
    QUARTERS_WINDOW, MAJOR_SHARE_PCT, MINOR_SHARE_PCT, TREND_RATIO,
    MIN_FAMILY_GAMES, ECO_SECTION_NAMES, STATUS_ORDER,
    get_family_period_counts, filter_counts, period_shares,
    classify_evolution, family_win_trend, get_family_acpl_by_period,
)
from .analysis_batches import (
    list_analysis_runs, get_batch_headline_delta, get_phase_accuracy_batch_delta,
    get_endgame_type_batch_delta, get_motif_batch_delta, get_new_blunders_this_run,
    get_batch_trend, get_batch_record_flags, get_batch_counter,
)
from .drills import (
    get_motif_drill_positions, get_decisive_moment_positions, build_drill_cards,
    drill_source_options,
)
from .srs import (
    SrsCard, get_due_cards, get_card_counts, add_cards, apply_rating, delete_card,
    TRANSFER_MIN_MOVES_AFTER,
    get_review_history, weekly_recall, learning_curve, recall_by_source,
    get_drilled_motifs, get_analyzed_move_series, get_motif_miss_series,
    compute_motif_transfer,
)
from .prep import open_opponent_connections, get_recent_form, get_opening_tendencies
from .ai_coach import (
    start_conversation, add_turn, record_feedback, get_conversation_messages,
    get_all_turns, get_profile, upsert_profile, count_turns_since,
    record_capability_gap, get_capability_gaps,
)
from .variations import (
    Variation, Annotation,
    compute_variation_fen,
    save_variation, update_variation_moves, delete_variation,
    list_variations, get_variation_annotations, upsert_annotation,
)
from .search import (
    PAGE_CANDIDATES, SETTINGS_CANDIDATES,
    build_dynamic_candidates, rank_candidates,
)

__all__ = [
    "TIME_PRESSURE_BUCKETS", "THINKING_TIME_BUCKETS",
    "GIANT_KILLING_UPSET_THRESHOLD", "GIANT_KILLING_COLLAPSE_THRESHOLD",
    "COMEBACK_WP_THRESHOLD", "COLLAPSE_WP_THRESHOLD",
    "get_cached_narrative", "save_narrative", "get_headline_stats",
    "get_rating_trajectory", "get_acpl_trajectory", "get_win_rate_by_color",
    "get_progress_by_month",
    "get_openings_table", "get_most_repeated_positions", "get_opening_ply_accuracy",
    "get_repertoire_holes", "get_position_fen", "get_position_analysis",
    "store_position_analysis", "FLIP_SCAN_MIN_TOTAL_GAMES",
    "get_opening_moves_by_year", "get_player_move_year_stats",
    "compute_dominant_move_flips", "summarize_position_timeline",
    "get_path_to_position", "resolve_move_squares",
    "SHARPNESS_BUCKETS", "PIECE_ORDER", "PIECE_NAME",
    "get_blunder_rate_by_time_pressure", "get_acpl_by_time_control",
    "get_phase_accuracy", "get_prior_outcome_performance",
    "get_session_position_performance", "get_day_hour_heatmap",
    "get_material_structure_table", "get_bishop_color_ending_performance", "get_piece_movement_patterns",
    "get_piece_blunder_by_phase", "get_piece_blunder_by_sharpness",
    "get_bishop_square_color_performance", "get_rook_king_backrank_performance",
    "get_castling_performance", "get_sharpness_blunder_correlation",
    "get_thinking_time_blunder_correlation", "get_decisive_moments",
    "get_instant_move_rate_by_phase", "get_instant_move_accuracy_by_legal_replies",
    "get_position_character_performance", "get_game_side_performance",
    "get_square_blunder_heatmap",
    "get_favorite_underdog_performance", "get_clock_pressure_by_rating_bucket",
    "get_clock_pressure_by_outcome", "get_clock_pressure_by_color", "get_clock_pressure_by_opening",
    "get_openings_by_rating_bucket", "get_session_rollup",
    "get_event_type_performance", "get_event_name_breakdown",
    "get_win_rate_by_rating_diff", "get_comeback_collapse_counts",
    "get_color_performance_by_rating", "get_giant_killing_counts",
    "get_nemesis_opponents", "get_giant_killing_collapse_causes",
    "get_giant_killing_rate_trend", "get_opponent_profile", "get_opponent_swindle_rate",
    "get_game_end_type_breakdown", "get_endgame_type_performance", "get_resignation_loss_causes",
    "get_resignation_time_pressure_trend",
    "RIM_SQL",
    "get_puzzle_sequences", "get_brilliant_candidates", "get_best_move_streaks",
    "get_blown_mates", "get_knight_rim_performance", "get_hallucination_blunders",
    "get_hallucination_context", "get_motif_breakdown", "motif_backfill_needed",
    "BLUNDER_FEST_THRESHOLD", "BRILLIANT_FIND_THRESHOLD", "NAIL_BITER_THRESHOLD",
    "get_game_badges", "get_game_explorer_table", "get_game_detail",
    "get_career_findings",
    "WINNING_WP", "LOST_WP", "SWINDLE_CHANCE_WP", "EVEN_WP", "HOLD_EVEN_MIN_MOVE",
    "CONVERSION_BANDS", "BUCKET_LABEL",
    "get_points_ledger", "classify_points_ledger", "summarize_buckets",
    "monthly_points", "conversion_breakdown", "get_failed_conversion_causes",
    "QUARTERS_WINDOW", "MAJOR_SHARE_PCT", "MINOR_SHARE_PCT", "TREND_RATIO",
    "MIN_FAMILY_GAMES", "ECO_SECTION_NAMES", "STATUS_ORDER",
    "get_family_period_counts", "filter_counts", "period_shares",
    "classify_evolution", "family_win_trend", "get_family_acpl_by_period",
    "list_analysis_runs", "get_batch_headline_delta", "get_phase_accuracy_batch_delta",
    "get_endgame_type_batch_delta", "get_motif_batch_delta", "get_new_blunders_this_run",
    "get_batch_trend", "get_batch_record_flags", "get_batch_counter",
    "get_motif_drill_positions", "get_decisive_moment_positions", "build_drill_cards",
    "drill_source_options",
    "SrsCard", "get_due_cards", "get_card_counts", "add_cards", "apply_rating", "delete_card",
    "TRANSFER_MIN_MOVES_AFTER",
    "get_review_history", "weekly_recall", "learning_curve", "recall_by_source",
    "get_drilled_motifs", "get_analyzed_move_series", "get_motif_miss_series",
    "compute_motif_transfer",
    "open_opponent_connections", "get_recent_form", "get_opening_tendencies",
    "Variation", "Annotation",
    "compute_variation_fen",
    "save_variation", "update_variation_moves", "delete_variation",
    "list_variations", "get_variation_annotations", "upsert_annotation",
    "start_conversation", "add_turn", "record_feedback", "get_conversation_messages",
    "get_all_turns", "get_profile", "upsert_profile", "count_turns_since",
    "record_capability_gap", "get_capability_gaps",
    "PAGE_CANDIDATES", "SETTINGS_CANDIDATES",
    "build_dynamic_candidates", "rank_candidates",
]

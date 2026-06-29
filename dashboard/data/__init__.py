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
)
from .openings import (
    get_openings_table, get_most_repeated_positions, get_opening_ply_accuracy,
    get_repertoire_holes, get_position_fen, get_position_analysis,
    store_position_analysis,
)
from .patterns import (
    SHARPNESS_BUCKETS, PIECE_ORDER, PIECE_NAME,
    get_blunder_rate_by_time_pressure, get_acpl_by_time_control,
    get_phase_accuracy, get_prior_outcome_performance,
    get_session_position_performance, get_day_hour_heatmap,
    get_material_structure_table, get_piece_movement_patterns,
    get_piece_blunder_by_phase, get_piece_blunder_by_sharpness,
    get_bishop_square_color_performance, get_rook_king_backrank_performance,
    get_castling_performance, get_sharpness_blunder_correlation,
    get_thinking_time_blunder_correlation, get_decisive_moments,
)
from .matchups import (
    get_win_rate_by_rating_diff, get_comeback_collapse_counts,
    get_color_performance_by_rating, get_giant_killing_counts,
    get_nemesis_opponents,
)
from .game_endings import get_game_end_type_breakdown, get_endgame_type_performance
from .tactical import (
    RIM_SQL,
    get_puzzle_sequences, get_brilliant_candidates, get_best_move_streaks,
    get_blown_mates, get_knight_rim_performance, get_hallucination_blunders,
    get_hallucination_context, get_motif_breakdown,
)
from .game_explorer import (
    BLUNDER_FEST_THRESHOLD, BRILLIANT_FIND_THRESHOLD, NAIL_BITER_THRESHOLD,
    get_lead_changes, get_game_badges, get_game_explorer_table, get_game_detail,
)
from .insights import get_career_findings
from .variations import (
    Variation, Annotation,
    compute_variation_fen,
    save_variation, update_variation_moves, delete_variation,
    list_variations, get_variation_annotations, upsert_annotation,
)

__all__ = [
    "TIME_PRESSURE_BUCKETS", "THINKING_TIME_BUCKETS",
    "GIANT_KILLING_UPSET_THRESHOLD", "GIANT_KILLING_COLLAPSE_THRESHOLD",
    "COMEBACK_WP_THRESHOLD", "COLLAPSE_WP_THRESHOLD",
    "get_cached_narrative", "save_narrative", "get_headline_stats",
    "get_rating_trajectory", "get_acpl_trajectory", "get_win_rate_by_color",
    "get_openings_table", "get_most_repeated_positions", "get_opening_ply_accuracy",
    "get_repertoire_holes", "get_position_fen", "get_position_analysis",
    "store_position_analysis",
    "SHARPNESS_BUCKETS", "PIECE_ORDER", "PIECE_NAME",
    "get_blunder_rate_by_time_pressure", "get_acpl_by_time_control",
    "get_phase_accuracy", "get_prior_outcome_performance",
    "get_session_position_performance", "get_day_hour_heatmap",
    "get_material_structure_table", "get_piece_movement_patterns",
    "get_piece_blunder_by_phase", "get_piece_blunder_by_sharpness",
    "get_bishop_square_color_performance", "get_rook_king_backrank_performance",
    "get_castling_performance", "get_sharpness_blunder_correlation",
    "get_thinking_time_blunder_correlation", "get_decisive_moments",
    "get_win_rate_by_rating_diff", "get_comeback_collapse_counts",
    "get_color_performance_by_rating", "get_giant_killing_counts",
    "get_nemesis_opponents",
    "get_game_end_type_breakdown", "get_endgame_type_performance",
    "RIM_SQL",
    "get_puzzle_sequences", "get_brilliant_candidates", "get_best_move_streaks",
    "get_blown_mates", "get_knight_rim_performance", "get_hallucination_blunders",
    "get_hallucination_context", "get_motif_breakdown",
    "BLUNDER_FEST_THRESHOLD", "BRILLIANT_FIND_THRESHOLD", "NAIL_BITER_THRESHOLD",
    "get_lead_changes", "get_game_badges", "get_game_explorer_table", "get_game_detail",
    "get_career_findings",
    "Variation", "Annotation",
    "compute_variation_fen",
    "save_variation", "update_variation_moves", "delete_variation",
    "list_variations", "get_variation_annotations", "upsert_annotation",
]

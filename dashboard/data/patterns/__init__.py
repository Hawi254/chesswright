"""Patterns page queries -- time pressure, time control, sharpness,
thinking time, game phase, session position, day/hour heatmap,
material-structure win rate, piece-movement/castling tendencies.

Split into eight single-topic submodules (largest-file modularization,
2026-07-17) from the original 1366-line patterns.py -- this __init__.py
re-exports every public name at the package's top level so every existing
call site (`import patterns; patterns.get_whatever(...)`, `from .patterns
import get_whatever`, `data.patterns.get_whatever(...)`) keeps working
without any changes -- only this package's internal layout changed, not
its public surface.
"""
from ._shared import SHARPNESS_BUCKETS, PIECE_ORDER, PIECE_NAME
from .time_and_session import (
    get_blunder_rate_by_time_pressure, get_acpl_by_time_control,
    get_phase_accuracy, get_prior_outcome_performance,
    get_session_position_performance, get_day_hour_heatmap,
    get_session_rollup,
)
from .material_structure import (
    get_material_structure_table, get_material_structure_bucket_table,
    get_bishop_color_ending_performance,
)
from .piece_movement import (
    get_piece_movement_patterns, get_piece_blunder_by_phase,
    get_piece_blunder_by_sharpness, get_bishop_square_color_performance,
    get_rook_king_backrank_performance, get_castling_performance,
)
from .rating_and_clock import (
    get_favorite_underdog_performance, get_clock_pressure_by_rating_bucket,
    get_clock_pressure_by_outcome, get_clock_pressure_by_color,
    get_clock_pressure_by_opening, get_openings_by_rating_bucket,
)
from .events import get_event_type_performance, get_event_name_breakdown
from .position_character import (
    get_position_character_performance, get_game_side_performance,
    get_square_blunder_heatmap, _classify_castling_config, _classify_action_side,
)
from .correlations import (
    get_sharpness_blunder_correlation, get_thinking_time_blunder_correlation,
    get_decisive_moments, get_instant_move_rate_by_phase,
    get_instant_move_accuracy_by_legal_replies,
)

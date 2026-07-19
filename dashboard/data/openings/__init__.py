"""Openings page queries -- split into three topic modules (largest-file
modularization follow-up, 2026-07-17) from the original 591-line
openings.py. This __init__.py re-exports every public name at the
package's top level so every existing call site (`from data import
openings as openings_module`, `from data.openings import (...)`, `from
.openings import get_repertoire_holes`, dashboard/data/__init__.py's own
re-export block) keeps working without any changes -- only this
package's internal layout changed, not its public surface.

Required deviation: this file also imports `config` directly, even
though no code here calls config.load_config() -- tests/integration/
test_data_layer.py's test_get_openings_table_uses_config_min_sample_size
does `monkeypatch.setattr(openings_module.config, "load_config", ...)`
where openings_module is `from data import openings as openings_module`,
which requires `config` to resolve as an attribute of this package, not
just of move_stats.py (the submodule that actually calls
config.load_config()). The patch still affects move_stats.py's and
position_analysis.py's own config.load_config() calls correctly, since
monkeypatch.setattr mutates the shared config module object itself (an
attribute rebind on config, not a rebind of a name in some other
module's __globals__).
"""
import config  # noqa: F401 (package-level attribute for openings_module.config monkeypatch)

from .move_stats import (
    INITIAL_FEN,
    get_opening_moves_from_fen, get_opening_ply_accuracy, get_openings_table,
    get_repertoire_holes, get_most_repeated_positions, get_path_to_position,
)
from .repertoire_evolution import (
    FLIP_SCAN_MIN_TOTAL_GAMES,
    get_opening_moves_by_year, get_player_move_year_stats,
    compute_dominant_move_flips, summarize_position_timeline,
)
from .position_analysis import (
    get_position_fen, resolve_move_squares, get_position_analysis,
    store_position_analysis,
)

__all__ = [
    "INITIAL_FEN", "FLIP_SCAN_MIN_TOTAL_GAMES",
    "get_opening_moves_from_fen", "get_opening_ply_accuracy", "get_openings_table",
    "get_repertoire_holes", "get_most_repeated_positions", "get_path_to_position",
    "get_opening_moves_by_year", "get_player_move_year_stats",
    "compute_dominant_move_flips", "summarize_position_timeline",
    "get_position_fen", "resolve_move_squares", "get_position_analysis",
    "store_position_analysis",
]

# points.py / openings.py Modularization — Design

Status: approved by user, pending self-review + doc-review gate
Date: 2026-07-17
Branch: `feature/eval-dedup-cache` (current branch)

## Context

The prior six-file modularization pass (`docs/superpowers/specs/2026-07-17-largest-file-modularization-design.md`)
explicitly deferred `dashboard/data/points.py` (600 lines) and
`dashboard/data/openings.py` (591 lines) to "keep this pass to the clearest
six offenders," while noting both already have real internal seams. This
design picks those two files back up as their own pass.

Both are shared data-layer modules, reached from both the live Streamlit
dashboard and (via `dashboard/` on `sys.path`, same mechanism confirmed in the
prior design) the in-progress React/FastAPI rewrite on `worktree-frontend-spike`.
Neither is a `dashboard/*_view.py` file and neither is being deleted by the
React migration, so — unlike the Streamlit view files — splitting them is not
throwaway work.

## Goals

- Split `dashboard/data/points.py` and `dashboard/data/openings.py` into
  smaller, single-topic modules with no behavior change — same public
  functions, same signatures, same call sites.
- Preserve every existing import path: `from data import points` /
  `from data import openings as openings_module` (both accessed as module
  objects in `tests/integration/test_data_layer.py`), `from data.openings import
  (...)` (`tests/unit/test_repertoire_evolution.py`,
  `tests/performance/test_query_perf.py`), `from .points import
  get_conversion_drill_positions, get_defense_drill_positions` and `from
  .openings import get_repertoire_holes` (`dashboard/data/drills.py`), and
  `dashboard/data/__init__.py`'s existing `from .points import (...)` /
  `from .openings import (...)` re-export blocks.
- Land as two independent, separately-tested, separately-committed units, in
  one plan doc — same convention as the six-file pass.

## Non-goals (explicit)

- **No behavior changes, no bug fixes folded in**, even if one is noticed
  while moving code — file a separate note instead of fixing it inline.
- **No other files.** This is scoped to exactly these two files, not a
  broader sweep of `dashboard/data/*.py`.
- **No reconciliation with `worktree-frontend-spike`**, for the same reason
  as the prior design: that's a separate concern for whoever eventually
  merges the branches.

## Architecture

Both files are Tier 1 in the prior design's sense — always imported, never
executed by literal file path — so both become true packages
(`foo.py` → `foo/__init__.py` + submodules), exactly like
`dashboard/data/patterns.py` and `dashboard/claude_narrative.py` were.

**Rule, same as the prior design:** submodules never import back through
their own package's `__init__.py` — they import from each other or from a
leaf module directly. `__init__.py` only imports *from* submodules, never the
reverse.

## Per-file breakdown

**`dashboard/data/points.py`** (600 lines) → `dashboard/data/points/`:
- `ledger.py` — `get_points_ledger`, `classify_points_ledger`,
  `summarize_buckets`, `monthly_points`, `conversion_breakdown`, all seven
  constants (`WINNING_WP`, `LOST_WP`, `SWINDLE_CHANCE_WP`, `EVEN_WP`,
  `HOLD_EVEN_MIN_MOVE`, `CONVERSION_BANDS`, `_POINTS`, `BUCKET_LABEL`), and the
  two small pure helpers `_phase_of_move`/`_clock_bucket`.
- `drill_positions.py` — `get_failed_conversion_causes`,
  `get_conversion_drill_positions`, `get_defense_drill_positions`. Grouped
  together (not split further) because the two drill-position functions'
  own docstrings describe them as reusing `get_failed_conversion_causes`'s
  exact CTE shapes. Imports `EVEN_WP` directly from `.ledger` (the one
  constant this group needs that lives in the other submodule — a direct
  sibling import, not through `__init__.py`) and `TIME_PRESSURE_BUCKETS` /
  `MATE_DISTANCE_BUCKETS` via `from .._shared import ...` /
  `from ..game_endings import ...` (two dots, since submodules now live one
  level deeper — same adjustment the `patterns/` split made).
- `__init__.py` — re-exports every name `dashboard/data/__init__.py`'s
  existing `from .points import (...)` block expects (`get_failed_conversion_causes`,
  the seven constants, `get_points_ledger`, `classify_points_ledger`,
  `summarize_buckets`, `monthly_points`, `conversion_breakdown`), **plus**
  `get_conversion_drill_positions` and `get_defense_drill_positions` (used
  directly by `dashboard/data/drills.py`'s `from .points import
  get_conversion_drill_positions, get_defense_drill_positions`, but not
  themselves re-exported one level up by `dashboard/data/__init__.py` —
  confirmed by reading that file, same shape as the prior design's
  `get_material_structure_bucket_table` case).

**`dashboard/data/openings.py`** (591 lines) → `dashboard/data/openings/`.
The prior design's deferred-work note described this file's seam as "move-
history vs. engine-backed position analysis" (two groups); reading the full
file surfaces a third, self-contained group — the "What Changed" time-sliced
repertoire-evolution block — so this design splits it three ways instead:
- `move_stats.py` — `get_opening_moves_from_fen`, `get_opening_ply_accuracy`,
  `get_openings_table`, `get_repertoire_holes`, `get_most_repeated_positions`,
  `get_path_to_position`, plus `INITIAL_FEN`, `_MAX_CACHED_PLY`,
  `_EMPTY_OPENING_MOVES`.
- `repertoire_evolution.py` — the Opening Tree "What Changed" scan and
  Explorer timeline headline: `FLIP_SCAN_MIN_TOTAL_GAMES`,
  `FLIP_SCAN_THRESHOLDS`, `_EMPTY_FLIPS`, `get_opening_moves_by_year`,
  `get_player_move_year_stats`, `_era_dominants`, `compute_dominant_move_flips`,
  `summarize_position_timeline`.
- `position_analysis.py` — `get_position_fen`, `resolve_move_squares`,
  `get_position_analysis`, `store_position_analysis`.
- `__init__.py` — re-exports everything `dashboard/data/__init__.py`'s
  existing `from .openings import (...)` block expects (`INITIAL_FEN`,
  `FLIP_SCAN_MIN_TOTAL_GAMES`, and all fourteen functions listed there),
  **plus** `get_repertoire_holes` for `dashboard/data/drills.py`'s `from
  .openings import get_repertoire_holes`.
  **Required deviation:** `__init__.py` must also carry its own `import
  config` statement, even though no code in `__init__.py` itself calls
  `config.load_config()`. `tests/integration/test_data_layer.py:266` does
  `monkeypatch.setattr(openings_module.config, "load_config", ...)` where
  `openings_module` is `from data import openings as openings_module` — this
  requires `config` to resolve as an attribute of the *package*, not just of
  whichever submodule (`move_stats.py`) actually calls it. Without this,
  `openings_module.config` raises `AttributeError` after the split. The
  patch still affects `move_stats.py`'s and `position_analysis.py`'s calls
  correctly, since `monkeypatch.setattr` mutates the shared `config` module
  object itself (an attribute rebind on `config`, not a rebind of a name in
  some other module's `__globals__`) — a different, simpler class of fix
  than the prior design's Task 3/Task 6 `__globals__` monkeypatch
  retargets, verified by reading exactly how `openings.py` calls
  `config.load_config()` today (via `config.` attribute access, never `from
  config import load_config`).
  No circular-import risk was found between the three submodules (checked
  every cross-call; none exists — each submodule's functions only call
  functions within the same submodule).

## Testing

Existing suite only — no new tests needed, every call site is preserved via
re-export. Full command: `python3 -m pytest` (Streamlit UI tests remain
opt-in and are not needed for this backend-only refactor, same as the prior
pass).

## Sequencing

Two independent units, two separate commits, in this order: `points.py` →
`openings.py`. Run the full test suite after each unit before starting the
next.

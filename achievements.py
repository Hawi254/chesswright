"""Achievements Service -- evaluates achievement criteria against real
gameplay/analysis data and records permanent unlocks. See
docs/superpowers/specs/2026-07-11-achievements-service-design.md.

Deliberately sqlite_conn only -- no DuckDB. This module is called from
sync.py/worker.py, standalone CLI pipelines with no DuckDB machinery of
their own; giving it a duck_conn would mean attaching DuckDB to those
processes for the first time, reintroducing the same-process DuckDB+
SQLite hazard the dashboard's per-PID snapshot mechanism exists to fix
(see project memory: duckdb_sqlite_same_process_hazard). Every check()
in this module is plain SQL/Python instead.

CATALOG starts empty here and is extended in place, further down this
same file, by each seed-achievement batch -- see the design spec's
seed catalog table for the full list and its grounding.
"""
import dataclasses
import datetime
import sqlite3
from typing import Callable

from config import load_config


@dataclasses.dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    category: str  # "streak" | "milestone" | "skill" | "narrative"
    triggers: frozenset  # subset of {"sync", "analysis"}
    check: Callable[[sqlite3.Connection, dict], object]  # -> str | bool | None


CATALOG: list[Achievement] = []


def evaluate(conn, trigger, config_path=None):
    """Runs every not-yet-unlocked catalog entry relevant to `trigger`.
    trigger=None runs the full catalog regardless of each entry's
    declared `triggers` -- used by the one-off backfill script (Task 8)
    to sweep existing history once. Each check() failure is caught,
    logged, and skipped -- one bad achievement must never abort the
    whole pass, let alone the sync/analysis pipeline calling this.
    Returns the list of achievement ids newly unlocked this call."""
    cfg = load_config(config_path)
    already_unlocked = {row[0] for row in conn.execute(
        "SELECT achievement_id FROM achievements_unlocked").fetchall()}
    newly_unlocked = []
    for achievement in CATALOG:
        if achievement.id in already_unlocked:
            continue
        if trigger is not None and trigger not in achievement.triggers:
            continue
        try:
            result = achievement.check(conn, cfg)
        except Exception as e:
            print(f"WARNING: achievement '{achievement.id}' check failed: {e}")
            continue
        if not result:
            continue
        source_game_id = result if isinstance(result, str) else None
        conn.execute(
            "INSERT INTO achievements_unlocked (achievement_id, unlocked_at, source_game_id) "
            "VALUES (?, ?, ?)",
            (achievement.id, datetime.datetime.now(datetime.timezone.utc).isoformat(),
             source_game_id))
        newly_unlocked.append(achievement.id)
    if newly_unlocked:
        conn.commit()
    return newly_unlocked


# ---------------------------------------------------------------------------
# Seed catalog, batch A: one-time board/outcome events.
# ---------------------------------------------------------------------------

GIANT_KILLING_UPSET_THRESHOLD = -300   # keep aligned with dashboard/data/_shared.py's copy
COMEBACK_WP_THRESHOLD = 0.10           # keep aligned with dashboard/data/_shared.py's copy


def _check_first_win(conn, cfg):
    row = conn.execute(
        "SELECT id FROM games WHERE outcome_for_player='win' "
        "ORDER BY utc_date, utc_time, id LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _check_giant_killer(conn, cfg):
    row = conn.execute(
        "SELECT id FROM games WHERE rating_diff <= ? AND outcome_for_player='win' "
        "ORDER BY utc_date, utc_time, id LIMIT 1",
        (GIANT_KILLING_UPSET_THRESHOLD,)
    ).fetchone()
    return row[0] if row else None


def _first_game_with_min_wp_at_most(conn, threshold, outcomes):
    """Shared by comeback_kid (batch A) and swindle_artist (batch D,
    Task 6) -- same "how low did the player's win probability go in this
    game" shape, differing only in the threshold and which final
    outcomes count. min_wp reuses the exact mover-POV-flip expression
    dashboard/data/game_explorer.get_game_badges uses for is_comeback,
    but as a plain SQLite GROUP BY (no window function needed for a MIN,
    unlike that function's LAG-based lead-change count), so it works
    outside the dashboard's DuckDB-only process."""
    placeholders = ",".join("?" * len(outcomes))
    row = conn.execute(f"""
        SELECT g.id
        FROM games g
        JOIN (
            SELECT game_id,
                   MIN(CASE WHEN is_player_move=1 THEN win_prob_before
                            ELSE 1 - win_prob_before END) AS min_wp
            FROM moves
            WHERE win_prob_before IS NOT NULL
            GROUP BY game_id
        ) m ON m.game_id = g.id
        WHERE m.min_wp <= ? AND g.outcome_for_player IN ({placeholders})
        ORDER BY g.utc_date, g.utc_time, g.id
        LIMIT 1
    """, (threshold, *outcomes)).fetchone()
    return row[0] if row else None


def _check_comeback_kid(conn, cfg):
    return _first_game_with_min_wp_at_most(conn, COMEBACK_WP_THRESHOLD, ("win", "draw"))


CATALOG.extend([
    Achievement("first_win", "First Win", "Win your first recorded game.",
                "milestone", frozenset({"sync"}), _check_first_win),
    Achievement("giant_killer", "Giant Killer",
                "Beat an opponent rated 300+ points above you.",
                "narrative", frozenset({"sync"}), _check_giant_killer),
    Achievement("comeback_kid", "Comeback Kid",
                "Win or draw a game you were nearly lost in.",
                "narrative", frozenset({"analysis"}), _check_comeback_kid),
])

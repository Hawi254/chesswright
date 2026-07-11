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

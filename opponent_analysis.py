"""Fetch and analyse an opponent's recent games in an isolated database.

The opponent's database lives at:
    {main_db_parent}/opponents/{username}/games.db

This keeps it completely separate from the user's own database: deleting an
opponent's data is just deleting that directory.

Called from prep_view.py's background thread. All state updates happen via
the on_progress callback and threading primitives, never Streamlit objects.

sync.run() calls ingest.ingest() internally, so no separate ingest step.
worker.run() acquires the global joblock (joblock.LOCK_PATH) -- if the user's
own batch is running this raises LockHeldError, which propagates out of the
thread and lands in prep_view's _state["error"].
"""
import pathlib
import threading

from config import load_config
import migrate
import sync
import worker
from worker import parse_duration
import annotate


def get_opponent_db_path(username: str) -> pathlib.Path:
    """Return the path for an opponent's isolated database, normalised to lowercase."""
    cfg = load_config()
    main_db = pathlib.Path(cfg["database"]["path"])
    return main_db.parent / "opponents" / username.lower() / "games.db"


def run_for_opponent(
    username: str,
    n_games: int,
    stop_event: threading.Event | None = None,
    on_progress=None,
) -> None:
    """Full pipeline for one opponent: fetch → ingest → analyse → annotate.

    on_progress: callable(step: str) -- called at each pipeline stage with a
    short stage name ("migrating", "fetching", "analyzing", "annotating").

    stop_event: cooperative stop passed into worker.run(); sync and annotate
    finish their current unit of work before honouring it.
    """
    cfg = load_config()
    db_path = get_opponent_db_path(username)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress("migrating")
    migrate.migrate(str(db_path))

    if on_progress:
        on_progress("fetching")
    sync.run(
        str(db_path),
        username,
        cfg["ingestion"]["queue_strategy"],
        cfg["ingestion"]["berserk_max_clock_fraction"],
        cfg["ingestion"]["variant_policy"],
        cfg["sync"]["request_timeout_seconds"],
        max_games=n_games,
    )

    if stop_event and stop_event.is_set():
        return

    if on_progress:
        on_progress("analyzing")
    worker.run(
        str(db_path),
        cfg["engine"]["depth"],
        cfg["engine"]["multipv"],
        cfg["engine"]["threads"],
        cfg["engine"]["hash_mb"],
        cfg["engine"]["pv_max_len"],
        cfg["engine"]["path"],
        n_games,
        parse_duration(cfg["worker"]["max_duration"]),
        cfg["worker"]["consecutive_failure_limit"],
        cfg["worker"]["commit_every_n_moves"],
        stop_event=stop_event,
    )

    if stop_event and stop_event.is_set():
        return

    if on_progress:
        on_progress("annotating")
    annotate.run(
        str(db_path),
        cfg["annotation"]["mate_score_cap_cp"],
        cfg["annotation"]["thresholds"],
        cfg["annotation"]["brilliant_material_threshold_cp"],
        cfg["annotation"]["puzzle"],
        cfg["annotation"]["best_move_streak"],
        None,  # all games
    )

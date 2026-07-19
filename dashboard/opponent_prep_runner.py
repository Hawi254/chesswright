"""Process-wide background job registry for opponent-scouting runs
(opponent_analysis.run_for_opponent), shared between the legacy
Streamlit Opponent Prep page (prep_view.py) and the FastAPI
/api/opponent-prep/* routes -- same shared-module pattern job_runner.py
already established for the Analysis Jobs page's background batches, so
this doesn't duplicate prep_view.py's thread-management globals a
second time inside api/main.py.

Module-level globals, not st.session_state / a request-scoped object --
a scout run belongs to this one local server process, the same
single-user/single-machine assumption job_runner.py documents.
"""
import threading

import job_runner
import joblock
import opponent_analysis

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop_event: threading.Event | None = None
_state: dict = {"status": "idle"}

STEP_LABELS = {
    "migrating":  "Setting up database...",
    "fetching":   "Fetching games from lichess...",
    "analyzing":  "Running Stockfish analysis...",
    "annotating": "Annotating moves...",
    "starting":   "Starting...",
}


def is_running() -> bool:
    with _lock:
        return _thread is not None and _thread.is_alive()


def get_state() -> dict:
    """A snapshot copy -- callers must never read the live dict while the
    worker thread is mid-write to it."""
    with _lock:
        return dict(_state)


def start(username: str, n_games: int) -> None:
    """Raises RuntimeError/joblock.LockHeldError synchronously (before
    spawning anything) if either guard is already held -- this process's
    own registry, or joblock's cross-process PID lock, or the user's own
    Analysis Jobs batch. Mirrors job_runner.start()'s exact pre-check
    shape so both callers (prep_view.py's st.warning, api/main.py's
    HTTPException 409) can catch the same two exception types."""
    global _thread, _stop_event
    with _lock:
        if _thread is not None and _thread.is_alive():
            raise RuntimeError("An opponent analysis is already running.")
        if job_runner.is_running():
            raise RuntimeError(
                "Your own analysis batch is running. Stop it from Analysis "
                "Jobs before starting opponent prep.")
        existing_lock = joblock.status()
        if existing_lock is not None and existing_lock.alive:
            raise joblock.LockHeldError(existing_lock)

        stop_event = threading.Event()
        _stop_event = stop_event
        _state.clear()
        _state.update(status="starting", username=username, step="starting", error=None)

    def on_progress(step: str) -> None:
        with _lock:
            _state.update(status="running", step=step)

    def target() -> None:
        try:
            opponent_analysis.run_for_opponent(
                username, n_games, stop_event=stop_event, on_progress=on_progress)
            with _lock:
                _state["status"] = "done"
        except Exception as exc:
            with _lock:
                _state.update(status="error", error=str(exc))

    thread = threading.Thread(target=target, daemon=True)
    with _lock:
        _thread = thread
    thread.start()


def load_existing(username: str) -> None:
    """Marks state as done for an already-scouted opponent without
    starting a new run -- used by prep_view.py's "Previously Analysed
    Opponents" quick-reload buttons, which need the status fragment to
    render straight into the report view for a username that was never
    started via this process's own start()."""
    with _lock:
        _state.clear()
        _state.update(status="done", username=username)


def stop() -> None:
    """Cooperative only -- sets the same threading.Event
    opponent_analysis.run_for_opponent() checks between pipeline stages.
    Does not kill the thread."""
    with _lock:
        if _stop_event is not None:
            _stop_event.set()
        _state["status"] = "stopping"

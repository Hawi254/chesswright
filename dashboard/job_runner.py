"""
Process-wide background job registry for worker.run() batches launched
from the Analysis Jobs view (BRIEF.md Q1/Q3): this view's whole point is
letting the user navigate elsewhere and come back, unlike onboarding's
deliberately-blocking wizard (onboarding_view.py's _render_running), so
a real background thread is the right tool here, not a bigger version of
onboarding's blocking spinner.

Module-level globals, not st.session_state -- a batch belongs to this one
local server process (the app is single-user/single-machine by design,
BRIEF.md S0), not to one browser tab's session. This also makes the
in-process duplicate-run guard free: there's exactly one slot, checked
here, before joblock.py's cross-process PID lock is even reached.
"""
import threading

import worker
import joblock

_lock = threading.Lock()
_thread = None
_stop_event = None
_run_seq = 0
_state: dict = {"status": "idle", "run_seq": 0}


def is_running() -> bool:
    with _lock:
        return _thread is not None and _thread.is_alive()


def get_state() -> dict:
    """A snapshot copy -- the UI (script) thread must never read the live
    dict while the worker thread is mid-write to it."""
    with _lock:
        return dict(_state)


def start(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
          max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves):
    """Raises RuntimeError synchronously (before spawning anything) if
    either guard is already held -- this process's own registry (Q3's
    cheap in-process layer) or joblock's cross-process PID lock (e.g. a
    `python3 worker.py` run from a terminal). Without this pre-check,
    joblock.acquire()'s own LockHeldError would still fire correctly, but
    only inside the background thread, a rerun later than necessary."""
    global _thread, _stop_event, _run_seq
    with _lock:
        if _thread is not None and _thread.is_alive():
            raise RuntimeError("A batch is already running in this app.")
        existing_lock = joblock.status()
        if existing_lock is not None and existing_lock.alive:
            raise joblock.LockHeldError(existing_lock)

        stop_event = threading.Event()
        _stop_event = stop_event
        _run_seq += 1
        # run_seq lets the UI dedupe its one-shot "batch finished" toast
        # against THIS run specifically -- get_state() returns a fresh
        # copy every poll, so the UI side can't just mutate a flag on it
        # and expect that to stick; comparing run_seq across reruns
        # (st.session_state on the caller's side) is what actually works.
        _state.clear()
        _state.update(status="starting", games_done=0, error=None, run_seq=_run_seq)

    def on_game_done(games_done, n_plies, finished):
        with _lock:
            _state.update(status="running", games_done=games_done,
                           last_n_plies=n_plies, last_finished=finished)

    def target():
        try:
            run_id = worker.run(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
                                max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves,
                                on_game_done=on_game_done, stop_event=stop_event)
            with _lock:
                _state.update(status="done", completed_run_id=run_id)
        except Exception as e:
            with _lock:
                _state.update(status="error", error=str(e))

    # daemon=True: if the desktop window is closed, the server process
    # (and this thread with it) exits immediately rather than hanging
    # around -- safe because worker.py's per-move commit means an abrupt
    # kill loses at most the in-flight move, the same resumability
    # property BRIEF.md already relies on for the onboarding subprocess
    # case.
    thread = threading.Thread(target=target, daemon=True)
    with _lock:
        _thread = thread
    thread.start()


def stop():
    """Cooperative only -- sets the same threading.Event worker.run()
    checks between moves (the identical checkpoint max_duration already
    uses in production, see worker.analyze_game()). Does not kill the
    thread; the in-progress game is left safely resumable."""
    with _lock:
        if _stop_event is not None:
            _stop_event.set()
            _state["status"] = "stopping"

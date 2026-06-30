"""Opponent Prep — scout a lichess player's recent games.

Analysis runs in a background thread (same model as analysis_jobs_view.py).
joblock prevents simultaneous Stockfish runs: worker.run() acquires the global
lock at LOCK_PATH, so starting opponent analysis while the user's own batch is
running raises LockHeldError inside the thread, which surfaces in _state["error"].

The @st.fragment(run_every="2s") pattern drives live status updates without
requiring the whole page to rerun on every poll -- confirmed pattern from
analysis_jobs_view.py.
"""
import pathlib
import threading

import streamlit as st

import job_runner
import joblock
import opponent_analysis
import data
from _common import get_config
from theme import thin_data_message

_lock = threading.Lock()
_thread: threading.Thread | None = None
_state: dict = {"status": "idle"}
_stop_event: threading.Event | None = None

_STEP_LABELS = {
    "migrating":  "Setting up database...",
    "fetching":   "Fetching games from lichess...",
    "analyzing":  "Running Stockfish analysis...",
    "annotating": "Annotating moves...",
    "starting":   "Starting...",
}


def _is_running() -> bool:
    with _lock:
        return _thread is not None and _thread.is_alive()


def _start(username: str, n_games: int) -> None:
    global _thread, _state, _stop_event
    stop = threading.Event()

    def _on_progress(step: str) -> None:
        with _lock:
            _state["step"] = step

    def _run() -> None:
        with _lock:
            _state.update({"status": "running", "username": username, "step": "starting"})
        try:
            opponent_analysis.run_for_opponent(
                username, n_games, stop_event=stop, on_progress=_on_progress
            )
            with _lock:
                _state["status"] = "done"
        except Exception as exc:
            with _lock:
                _state.update({"status": "error", "error": str(exc)})

    with _lock:
        _state = {"status": "starting", "username": username, "step": "starting"}
        _stop_event = stop
        _thread = threading.Thread(target=_run, daemon=True)
        _thread.start()


def _stop() -> None:
    with _lock:
        if _stop_event:
            _stop_event.set()
        _state["status"] = "stopping"


@st.fragment(run_every="2s")
def _status_fragment() -> None:
    """Polls thread state every 2s; fires one full rerun when analysis completes."""
    with _lock:
        state = dict(_state)
    status = state.get("status", "idle")

    if status in ("starting", "running", "stopping"):
        step = state.get("step", "starting")
        label = _STEP_LABELS.get(step, step)
        username = state.get("username", "")
        st.info(f"Analysing **{username}**: {label}")
        if status not in ("stopping",):
            if st.button("Stop analysis"):
                _stop()
                st.rerun()
        return

    if status == "done" and not st.session_state.get("_prep_done_acked"):
        st.session_state["_prep_done_acked"] = True
        st.rerun()


def _render_scout_report(username: str) -> None:
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        st.warning(f"No analysis data found for **{username}**.")
        return

    try:
        n = duck_conn.execute(
            "SELECT COUNT(*) FROM db.games WHERE analysis_status='done'"
        ).fetchone()[0]

        st.success(f"Analysis complete — **{n}** game(s) analysed for **{username}**.")
        if n < 5:
            st.warning(thin_data_message(n, 5))

        form_df = data.get_recent_form(duck_conn)
        tendencies_df = data.get_opening_tendencies(duck_conn)

        if not form_df.empty:
            st.subheader("Opening Repertoire")
            st.caption("Openings with 3+ analysed games, by color.")
            col1, col2 = st.columns(2)
            col_map = {
                "opening": "Opening", "n_games": "Games",
                "score_pct": "Score %", "avg_cpl": "ACPL",
            }
            with col1:
                w = form_df[form_df.color == "white"].drop(columns=["color"])
                if not w.empty:
                    st.markdown("**As White**")
                    st.dataframe(w.rename(columns=col_map), use_container_width=True,
                                 hide_index=True)
            with col2:
                b = form_df[form_df.color == "black"].drop(columns=["color"])
                if not b.empty:
                    st.markdown("**As Black**")
                    st.dataframe(b.rename(columns=col_map), use_container_width=True,
                                 hide_index=True)

        if not tendencies_df.empty:
            st.subheader("Where They Go Wrong")
            st.caption("Openings sorted by blunder rate — target these in your prep.")
            st.dataframe(
                tendencies_df.rename(columns={
                    "opening": "Opening", "color": "Color", "n_games": "Games",
                    "avg_cpl": "ACPL", "blunder_pct": "Blunder %",
                }),
                use_container_width=True,
                hide_index=True,
            )

        if form_df.empty and tendencies_df.empty:
            st.info(
                "Not enough annotated games to compute a report. "
                "Re-run after more games finish analysis, or try fetching more games."
            )
    finally:
        for conn in (sqlite_conn, duck_conn):
            try:
                conn.close()
            except Exception:
                pass


def _render_prev_opponents() -> None:
    """List previously analysed opponents with quick-reload buttons."""
    cfg = get_config()
    opponents_dir = pathlib.Path(cfg["database"]["path"]).parent / "opponents"
    if not opponents_dir.exists():
        return
    done = [
        d.name for d in sorted(opponents_dir.iterdir())
        if d.is_dir() and (d / "games.db").exists()
    ]
    if not done:
        return
    st.subheader("Previously Analysed Opponents")
    for name in done:
        if st.button(name, key=f"prev_{name}"):
            with _lock:
                _state.update({"status": "done", "username": name})
            st.rerun()


def render() -> None:
    st.title("Opponent Prep")
    st.write(
        "Fetch and analyse an opponent's recent games to see their opening repertoire "
        "and where they tend to go wrong. "
        "Analysis runs locally using your Stockfish installation."
    )

    # ---------- Input form ----------
    # _prep_username is injected by insights_view when navigating from the
    # "Scout this opponent" button on the Toughest opponent finding.
    preset_username = st.session_state.pop("_prep_username", "")
    with st.form("opp_prep_form"):
        username = st.text_input("Lichess username", value=preset_username,
                                 placeholder="e.g. DrNykterstein")
        n_games = st.slider("Games to fetch", min_value=10, max_value=200, value=50, step=10)
        submitted = st.form_submit_button("Fetch & Analyse", type="primary")

    if submitted:
        username = username.strip()
        if not username:
            st.warning("Enter a lichess username.")
        else:
            lock = joblock.status()
            if _is_running():
                st.warning("An opponent analysis is already running.")
            elif job_runner.is_running():
                st.warning(
                    "Your own analysis batch is running. "
                    "Stop it from Analysis Jobs before starting opponent prep."
                )
            elif lock is not None and lock.alive:
                st.warning(
                    f"An analysis process (PID {lock.pid}) is running outside this app. "
                    "Stop it before starting opponent prep."
                )
            else:
                st.session_state.pop("_prep_done_acked", None)
                _start(username, n_games)
                st.rerun()

    # ---------- Live status (polls every 2s while running) ----------
    _status_fragment()

    # ---------- Post-analysis results ----------
    with _lock:
        state = dict(_state)
    status = state.get("status", "idle")

    if status == "error":
        st.error(f"Analysis failed: {state.get('error', 'Unknown error')}")
        st.caption("Check that the username is spelled correctly and Stockfish is installed.")
    elif status == "done":
        _render_scout_report(state.get("username", ""))
    elif status == "idle":
        _render_prev_opponents()

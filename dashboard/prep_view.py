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

import streamlit as st

import opponent_prep_runner
import joblock
import data
import pro_gate
from _common import get_config, get_connections
from theme import thin_data_message


@st.fragment(run_every="2s")
def _status_fragment() -> None:
    """Polls thread state every 2s and renders all terminal states here.

    Terminal states (error, done, idle) are rendered inside the fragment
    rather than triggering st.rerun() to notify the main body. Calling
    st.rerun() (full-app) from within a run_every fragment causes a
    "fragment does not exist anymore" error: the full rerun replaces the
    fragment with a new ID, then the old run_every callback fires against
    the now-gone ID. Keeping all rendering in the fragment avoids this.
    """
    state = opponent_prep_runner.get_state()
    status = state.get("status", "idle")

    if status in ("starting", "running", "stopping"):
        step = state.get("step", "starting")
        label = opponent_prep_runner.STEP_LABELS.get(step, step)
        username = state.get("username", "")
        st.info(f"Analysing **{username}**: {label}")
        if status != "stopping":
            if st.button("Stop analysis"):
                opponent_prep_runner.stop()
                st.rerun(scope="fragment")
        return

    if status == "error":
        st.error(f"Analysis failed: {state.get('error', 'Unknown error')}")
        st.caption("Check that the username is spelled correctly and Stockfish is installed.")
    elif status == "done":
        # Transient connection races (the DuckDB ATTACH retry in
        # _common.py covers the known one) shouldn't surface as a raw
        # traceback on a page that just told the user "Analysis
        # complete" -- match the "explain, don't crash" handling every
        # other AI/DB-backed panel in this app already uses.
        try:
            _render_scout_report(state.get("username", ""))
        except Exception as e:
            st.error(f"Couldn't load the scout report: {e}")
            st.caption("Try again -- this is usually a transient database hiccup.")
    elif status == "idle":
        _render_prev_opponents()


def _render_scout_report(username: str) -> None:
    sqlite_conn, duck_conn = data.open_opponent_connections(username)
    if duck_conn is None:
        st.warning(f"No analysis data found for **{username}**.")
        return

    try:
        # A bare COUNT(*) always returns exactly one row -- None here means
        # something went wrong beneath the query itself (a transient
        # connection race), not a legitimate empty result. Same "explain
        # what's missing, don't crash" guard as data/_shared.py's
        # _fetchone_scalar, inlined here rather than reaching across
        # packages for a private helper.
        row = duck_conn.execute(
            "SELECT COUNT(*) FROM db.games WHERE analysis_status='done'"
        ).fetchone()
        n = row[0] if row is not None else 0

        st.success(f"Analysis complete — **{n}** game(s) analysed for **{username}**.")
        if n < 5:
            st.warning(thin_data_message(n, 5))

        repertoire_df = data.get_repertoire(duck_conn)

        if not repertoire_df.empty:
            st.subheader("Opening Repertoire")
            st.caption("Openings with 3+ analysed games, by color. Sorted by blunder rate.")
            col_map = {
                "opening": "Opening", "n_games": "Games",
                "score_pct": "Score %", "avg_cpl": "ACPL", "blunder_pct": "Blunder %",
            }
            sorted_df = repertoire_df.sort_values("blunder_pct", ascending=False, na_position="last")
            st.dataframe(
                sorted_df.rename(columns=col_map),
                width='stretch', hide_index=True,
            )
        else:
            st.info(
                "Not enough annotated games to compute a report. "
                "Re-run after more games finish analysis, or try fetching more games."
            )

        with st.container(border=True):
            st.subheader("Tournament Prep Report")
            st.caption(
                "A downloadable prep sheet combining their repertoire with your "
                "personal record against them."
            )
            if not pro_gate.is_pro_active():
                st.info(
                    "**Tournament Prep Report** is a Chesswright Pro feature — combine "
                    "what this opponent tends to play with your own personal record "
                    "against them in one downloadable document. "
                    "Upgrade at [chesswright.gumroad.com](https://chesswright.gumroad.com)."
                )
            else:
                try:
                    from chesswright_pro import tournament_prep
                except ImportError:
                    st.error(
                        "Pro is licensed but the chesswright_pro package couldn't be "
                        "imported. Try reinstalling it."
                    )
                else:
                    _, main_duck_conn = get_connections()
                    tournament_prep.render_tournament_prep_report(
                        username, n, repertoire_df, main_duck_conn
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
            opponent_prep_runner.load_existing(name)
            st.rerun(scope="fragment")


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
            try:
                opponent_prep_runner.start(username, n_games)
            except (RuntimeError, joblock.LockHeldError) as e:
                st.warning(str(e))
            else:
                st.rerun()

    # ---------- Live status + results (fragment handles all states) ----------
    _status_fragment()

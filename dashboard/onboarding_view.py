"""
First-run onboarding wizard (BRIEF.md Phase B). The original personal
project never needed this -- its single user already knew their own
username, already had Stockfish installed, and accepted the slow
pipeline as a given after watching it get re-benchmarked by hand. An
installer of a packaged app has none of that context, so this page
exists to give it to them honestly: a real, measured time estimate from
THEIR OWN hardware, not a number copy-pasted from someone else's.

Linear wizard, steps tracked in st.session_state["onboard_step"]:
welcome -> username -> engine -> fetch -> calibrate -> plan -> running -> done

Re-visiting this page after onboarding is already complete (db has
games, player.name is set) skips straight to a small "add more games"
shortcut into the fetch/plan/running steps, rather than forcing the
whole wizard again.
"""
import requests
import streamlit as st

import annotate
import config as config_module
import sync
import worker
from _common import get_config, resolve_db_path, get_sqlite_connection

MAX_FETCH_GAMES = 100   # generous enough to cover most starter-batch choices below
CALIBRATION_PLIES = 10


def _already_onboarded(db_path):
    cfg = get_config()
    if cfg["player"]["name"] == "CHANGE_ME":
        return False
    conn = get_sqlite_connection(db_path)
    n = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    return n > 0


def _set_step(step):
    st.session_state["onboard_step"] = step
    st.rerun()


def render(overview_page):
    db_path = resolve_db_path()
    step = st.session_state.get("onboard_step")
    if step is None:
        step = "status" if _already_onboarded(db_path) else "welcome"
        st.session_state["onboard_step"] = step

    st.title("Welcome to Chesswright")

    if step == "status":
        _render_status(db_path, overview_page)
    elif step == "welcome":
        _render_welcome()
    elif step == "username":
        _render_username()
    elif step == "engine":
        _render_engine()
    elif step == "fetch":
        _render_fetch(db_path)
    elif step == "calibrate":
        _render_calibrate(db_path)
    elif step == "plan":
        _render_plan(db_path, overview_page)
    elif step == "running":
        _render_running(db_path)
    elif step == "done":
        _render_done(overview_page)


def _render_status(db_path, overview_page):
    cfg = get_config()
    conn = get_sqlite_connection(db_path)
    total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    analyzed = conn.execute("SELECT COUNT(*) FROM games WHERE analysis_status='done'").fetchone()[0]
    st.success(f"Already set up for **{cfg['player']['name']}** -- "
               f"{analyzed:,} of {total:,} games analyzed so far.")
    st.caption("This wizard is for first-time setup. You can fetch more games or run another "
               "analysis batch below, or just head to the dashboard.")
    col1, col2 = st.columns(2)
    if col1.button("Fetch more games and analyze another batch"):
        _set_step("fetch")
    if col2.button("Go to dashboard"):
        st.switch_page(overview_page)


def _render_welcome():
    st.markdown(
        "This app analyzes your lichess games with a real chess engine "
        "(Stockfish) to find patterns in how you actually play. Before we "
        "start, there's one thing worth being honest about up front:")
    st.warning(
        "**Engine analysis is genuinely slow.** A real chess engine search "
        "takes real time per move -- there's no way around that. We're not "
        "going to hide this or make vague promises. In the next couple of "
        "steps, we'll measure exactly how fast it runs **on your own "
        "computer**, using a few of your own real games, so the time "
        "estimate you see is a real measurement, not a guess.")
    st.markdown(
        "Everything else in the app works immediately on whatever's been "
        "analyzed so far -- you don't need to wait for a full analysis to "
        "start seeing real findings about your games.")
    if st.button("Get started", type="primary"):
        _set_step("username")


def _render_username():
    st.subheader("Step 1 of 5: your lichess username")
    cfg = get_config()
    current = cfg["player"]["name"]
    default = "" if current == "CHANGE_ME" else current
    username = st.text_input("Lichess username", value=default,
                              placeholder="exactly as it appears in your profile URL")
    if st.button("Continue", type="primary", disabled=not username.strip()):
        config_module.set_player_name(username.strip())
        _set_step("engine")


def _render_engine():
    st.subheader("Step 2 of 5: Stockfish")
    path = worker.find_engine_path(None)
    if path:
        st.success(f"Found Stockfish at `{path}`.")
        if st.button("Continue", type="primary"):
            _set_step("fetch")
    else:
        st.error("No Stockfish installation found on this computer.")
        st.markdown(
            "This app never bundles or auto-downloads the engine itself "
            "(it's a separate, independently-licensed project) -- please "
            "install it yourself, then come back:\n\n"
            "- **Windows / macOS / Linux**: download from "
            "[stockfishchess.org/download](https://stockfishchess.org/download/)\n"
            "- **Linux (apt-based)**: `sudo apt install stockfish`\n"
            "- **macOS (Homebrew)**: `brew install stockfish`\n\n"
            "Once installed, make sure it's on your system PATH (or set "
            "`engine.path` directly in `config.yaml`), then click below.")
        if st.button("I've installed it -- check again"):
            st.rerun()


def _render_fetch(db_path):
    st.subheader("Step 3 of 5: fetch a few real games")
    cfg = get_config()
    st.markdown(
        f"We'll pull up to **{MAX_FETCH_GAMES}** of your most recent games from "
        f"lichess (`{cfg['player']['name']}`) -- enough to measure real timing "
        "and give you a starter batch to analyze. This does not touch lichess "
        "in any way other than a normal read of your public game history.")
    if st.button("Fetch my games", type="primary"):
        with st.spinner("Talking to lichess..."):
            try:
                sync.run(db_path, cfg["player"]["name"], cfg["ingestion"]["queue_strategy"],
                          cfg["ingestion"]["berserk_max_clock_fraction"],
                          cfg["ingestion"]["variant_policy"],
                          cfg["sync"]["request_timeout_seconds"], max_games=MAX_FETCH_GAMES)
            except requests.exceptions.HTTPError as e:
                # Confirmed live against the real API: an unknown username
                # raises exactly this (404), not a friendlier lichess-side
                # error -- the default str(e) includes the raw request URL
                # with query params, which is correct but not something a
                # non-technical installer should have to parse.
                if e.response is not None and e.response.status_code == 404:
                    st.error(f"No lichess account found for '{cfg['player']['name']}'. Go back "
                             "and double-check the spelling (it's case-sensitive).")
                else:
                    st.error(f"Lichess returned an error ({e.response.status_code if e.response else '?'}) "
                             "-- try again in a moment.")
                return
            except requests.exceptions.RequestException as e:
                st.error(f"Couldn't reach lichess: {e}. Check your internet connection and try again.")
                return
        conn = get_sqlite_connection(db_path)
        n = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        if n == 0:
            st.error(f"No games found for '{cfg['player']['name']}' -- check the username "
                     "is correct (case-sensitive, no @ prefix) and that the account has "
                     "public rated games.")
            return
        st.success(f"{n:,} game(s) ready to analyze.")
        st.session_state["onboard_fetched_count"] = n
        _set_step("calibrate")


def _render_calibrate(db_path):
    st.subheader("Step 4 of 5: measure real timing on your computer")
    cfg = get_config()
    st.markdown(
        f"We'll analyze {CALIBRATION_PLIES} real moves from your own games, at the "
        f"settings this app is configured with (depth={cfg['engine']['depth']}, "
        f"multipv={cfg['engine']['multipv']}), and time it for real -- this is the "
        "exact same kind of timing dry run used to set those defaults in the "
        "first place, just run fresh on your hardware instead of someone else's.")
    if st.button("Run calibration", type="primary"):
        with st.spinner(f"Analyzing {CALIBRATION_PLIES} real moves..."):
            try:
                avg_seconds, plies_measured = worker.calibrate(
                    db_path, cfg["engine"]["depth"], cfg["engine"]["multipv"],
                    cfg["engine"]["threads"], cfg["engine"]["hash_mb"],
                    cfg["engine"]["pv_max_len"], cfg["engine"]["path"],
                    max_plies=CALIBRATION_PLIES)
            except RuntimeError as e:
                st.error(str(e))
                return
        st.session_state["onboard_avg_seconds_per_move"] = avg_seconds
        st.success(f"Measured {avg_seconds:.2f}s/move, averaged over {plies_measured} "
                    "real moves just analyzed on this computer.")
        _set_step("plan")


def _render_plan(db_path, overview_page):
    st.subheader("Step 5 of 5: pick your starter batch")
    avg_seconds = st.session_state.get("onboard_avg_seconds_per_move")
    if avg_seconds is None:
        st.warning("Calibration result not found -- please run calibration again.")
        if st.button("Back to calibration"):
            _set_step("calibrate")
        return

    conn = get_sqlite_connection(db_path)
    available = conn.execute(
        "SELECT COUNT(*) FROM games WHERE analysis_status IN ('pending','in_progress')"
    ).fetchone()[0]
    avg_plies_row = conn.execute("SELECT AVG(num_plies) FROM games WHERE num_plies > 0").fetchone()
    avg_plies_per_game = avg_plies_row[0] or 80  # 80 is a reasonable fallback, not a real measurement

    if available == 0:
        st.success("Every fetched game is already analyzed -- nothing left to do here.")
        if st.button("Go to dashboard", type="primary"):
            st.switch_page(overview_page)
        return

    default_batch = min(30, available)
    batch_size = st.slider("Games to analyze now", 1, available, default_batch)
    est_minutes = batch_size * avg_plies_per_game * avg_seconds / 60
    st.info(
        f"Based on the {avg_seconds:.2f}s/move just measured on your computer and an "
        f"average of ~{avg_plies_per_game:.0f} moves/game in your own games: analyzing "
        f"**{batch_size} games is estimated to take about {est_minutes:.0f} minutes.** "
        "This is a real measurement from your own hardware, not a generic estimate -- "
        "actual time can still vary game to game (longer games, sharper positions).")
    st.caption("You don't have to wait for this to finish to start exploring -- the "
               "dashboard already works on whatever's been analyzed so far.")
    if st.button("Start analyzing", type="primary"):
        st.session_state["onboard_batch_size"] = batch_size
        _set_step("running")


def _render_running(db_path):
    st.subheader("Analyzing your starter batch...")
    batch_size = st.session_state.get("onboard_batch_size", 1)
    cfg = get_config()

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    completed = {"games_done": 0}

    def on_game_done(games_done, _n_plies, _finished):
        # Called in-process, in between games -- Streamlit elements can be
        # updated mid-script-execution like this without a rerun. Calling
        # worker.run() directly (not as a `sys.executable worker.py`
        # subprocess, the original approach) is required for this to work
        # once frozen by PyInstaller, since there's no separate worker.py
        # script file to launch that way inside a bundled app -- a real
        # gap found during Phase C packaging, not a stylistic preference.
        completed["games_done"] = games_done
        progress_bar.progress(min(1.0, games_done / batch_size) if batch_size else 1.0)
        status_text.text(f"{games_done} of {batch_size} games analyzed so far...")

    error = None
    try:
        worker.run(db_path, cfg["engine"]["depth"], cfg["engine"]["multipv"],
                   cfg["engine"]["threads"], cfg["engine"]["hash_mb"], cfg["engine"]["pv_max_len"],
                   cfg["engine"]["path"], max_games=batch_size, max_duration_s=None,
                   consecutive_failure_limit=cfg["worker"]["consecutive_failure_limit"],
                   commit_every_n_moves=cfg["worker"]["commit_every_n_moves"],
                   on_game_done=on_game_done)
    except Exception as e:
        error = e

    progress_bar.progress(1.0)
    if error is not None:
        status_text.error(
            f"The analysis run stopped with an error: {error}. {completed['games_done']} game(s) "
            "analyzed before the error are safe and saved -- try running another batch from the "
            "dashboard later.")
        _set_step("done")
        return

    # worker.py only writes raw evals -- CPL/classification/sharpness/etc.
    # are a separate recompute pass (annotate.py). The original project
    # has a standing rule that skipping this step silently leaves the
    # dashboard showing stale numbers (caught live there once: 770 newly-
    # analyzed games sat with no CPL for a while before anyone noticed).
    # An installer doing this through a GUI wizard has no way to know that
    # rule exists, let alone run a second script themselves -- so this
    # step runs automatically rather than being left as a follow-up.
    status_text.text("Computing accuracy/classification numbers from the new evals...")
    annotate.run(db_path, cfg["annotation"]["mate_score_cap_cp"], cfg["annotation"]["thresholds"],
                 cfg["annotation"]["brilliant_material_threshold_cp"], cfg["annotation"]["puzzle"],
                 cfg["annotation"]["best_move_streak"], game_id=None)
    status_text.success(f"Done -- {completed['games_done']} games analyzed.")
    _set_step("done")


def _render_done(overview_page):
    st.success("Your starter batch is ready -- accuracy numbers are computed and the "
               "dashboard is up to date. Future batches you run from here do the same "
               "automatically; if you ever run worker.py by hand from a terminal instead, "
               "remember to run annotate.py afterward too.")
    if st.button("Go to dashboard", type="primary"):
        st.switch_page(overview_page)

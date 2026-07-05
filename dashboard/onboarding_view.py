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
import pathlib
import platform
import shutil
import stat

import requests
import streamlit as st

import annotate
import config as config_module
import sync
import sync_chesscom
import worker
import components.native_file_picker as native_file_picker
from _common import get_config, get_connections, resolve_db_path, get_sqlite_connection

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


def _refresh_duck_snapshot():
    """Games/analysis just landed in the live database -- duck-side reads
    run against a private snapshot (see _common.py's snapshot-isolation
    comment) that only picks up changes at explicit refresh points.
    Everywhere else the sidebar "Refresh data" button is that point, but a
    user leaving this wizard has never seen that button -- without this, a
    first run would land on an Overview showing zero games, violating the
    honest-first-run rule."""
    get_connections()[1].refresh_snapshot()


def render(overview_page):
    db_path = resolve_db_path()
    step = st.session_state.get("onboard_step")
    if step is None:
        step = "status" if _already_onboarded(db_path) else "welcome"
        st.session_state["onboard_step"] = step

    st.title("Sync Games" if step == "status" else "Welcome to Chesswright")

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
    elif step == "fetch_chesscom":
        _render_fetch_chesscom(db_path)
    elif step == "calibrate":
        _render_calibrate(db_path)
    elif step == "plan":
        _render_plan(db_path, overview_page)
    elif step == "running":
        _render_running(db_path)
    elif step == "fetch_done":
        _render_fetch_done(overview_page)
    elif step == "done":
        _render_done(overview_page)


def _render_status(db_path, overview_page):
    cfg = get_config()
    conn = get_sqlite_connection(db_path)
    total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    analyzed = conn.execute("SELECT COUNT(*) FROM games WHERE analysis_status='done'").fetchone()[0]
    st.success(f"Ready -- **{cfg['player']['name']}**, "
               f"{analyzed:,} of {total:,} games analyzed.")

    chesscom_username = cfg["player"].get("chesscom_username")
    cols = st.columns(3 if chesscom_username else 2)
    if cols[0].button("Fetch new games from lichess"):
        st.session_state["onboard_returning"] = True
        _set_step("fetch")
    if chesscom_username and cols[1].button("Fetch new games from chess.com"):
        st.session_state["onboard_returning"] = True
        _set_step("fetch_chesscom")
    if cols[-1].button("Go to dashboard"):
        st.switch_page(overview_page)
    if not chesscom_username:
        st.caption("Also play on chess.com? Connect an account on the Settings page "
                    "to sync those games in too.")


def _render_welcome():
    st.markdown(
        "This app analyzes your lichess games with a real chess engine "
        "(Stockfish) to find patterns in how you actually play. Before we "
        "start, there's one thing worth being honest about up front:")
    st.info(
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


def _engine_install_instructions():
    """OS-specific, package-manager-first / manual-download-fallback
    instructions -- replaces the old flat one-sentence-plus-link version.
    Never bundles or auto-downloads anything itself (BRIEF.md S1's
    deliberately-kept GPL boundary -- the app is never the distributor),
    but the manual path is no longer the ONLY path: most installs are a
    single recommended command away."""
    system = platform.system()
    if system == "Linux":
        st.markdown(
            "**Recommended -- via your package manager:** open a terminal "
            "and run:\n```\nsudo apt install stockfish\n```\n"
            "(Debian/Ubuntu; use your distro's equivalent -- `dnf install "
            "stockfish`, `pacman -S stockfish`, etc. -- if different). Then "
            "click **\"Check again\"** below.\n\n"
            "**Manual download:** "
            "[stockfishchess.org/download](https://stockfishchess.org/download/) "
            "(Linux build) -- extract it, then use the picker below to "
            "select the extracted binary.")
    elif system == "Darwin":
        st.markdown(
            "**Recommended -- via Homebrew:** open Terminal and run:\n"
            "```\nbrew install stockfish\n```\n"
            "(needs [Homebrew](https://brew.sh) installed first). Then "
            "click **\"Check again\"** below.\n\n"
            "**Manual download:** "
            "[stockfishchess.org/download](https://stockfishchess.org/download/) "
            "(macOS build) -- then use the picker below to select it. "
            "macOS may block an unsigned binary on first run -- right-click "
            "it, choose **Open**, then confirm.")
    else:
        st.markdown(
            "**Download:** "
            "[stockfishchess.org/download](https://stockfishchess.org/download/) "
            "(Windows build, a `.zip`). Extract it anywhere (e.g. your "
            "Desktop), then use the picker below to select the `.exe` "
            "file inside the extracted folder.")


def _render_engine_picker():
    """Generalized beyond Stockfish specifically: ANY UCI-compatible chess
    engine the user already has works, since worker.py talks to it over
    the standard UCI protocol either way (chess.engine.SimpleEngine.
    popen_uci -- not Stockfish-specific code). Stockfish is recommended
    (the instructions above point there), not required. Saved into this
    app's own data directory (same copy-not-reference posture db_import.py
    already uses) rather than referenced in place, and validated with a
    real UCI handshake before being accepted -- rejects the wrong file
    with a clear message instead of failing on the next real analysis
    run."""
    st.warning(
        "Only upload a binary you obtained directly from "
        "[stockfishchess.org/download](https://stockfishchess.org/download/) "
        "or the official release page of another UCI engine. "
        "This app will execute the file you select — do not upload a file "
        "from an untrusted source.")

    # Real native OS file dialog when running in the packaged desktop
    # app (see components/native_file_picker); st.file_uploader stays
    # as the always-available fallback for the plain `streamlit run`
    # dev workflow, where no native dialog exists at all.
    picked_path = native_file_picker.pick(
        "engine", label="Browse for its executable file (native dialog)…",
        key="engine_native_picker")
    uploaded = st.file_uploader(
        "Already have a UCI chess engine installed (Stockfish or another)? "
        "Browse for its executable file:")

    engines_dir = pathlib.Path(config_module.DEFAULT_CONFIG_PATH).parent / "engines"
    engines_dir.mkdir(parents=True, exist_ok=True)
    if picked_path:
        dest = engines_dir / pathlib.Path(picked_path).name  # .name strips any directory traversal
        shutil.copy2(picked_path, dest)
    elif uploaded is not None:
        dest = engines_dir / pathlib.Path(uploaded.name).name  # .name strips any directory traversal
        dest.write_bytes(uploaded.getvalue())
    else:
        return
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    with st.spinner("Checking it speaks UCI..."):
        try:
            engine_name = worker.validate_engine_path(str(dest))
        except RuntimeError as e:
            dest.unlink(missing_ok=True)
            st.error(str(e))
            return
    config_module.set_engine_path(str(dest))
    st.success(f"Confirmed: {engine_name}.")
    _set_step("fetch")


def _render_engine():
    st.subheader("Step 2 of 5: chess engine")
    path = worker.find_engine_path(None)
    if path:
        st.success(f"Found a chess engine at `{path}`.")
        if st.button("Continue", type="primary"):
            _set_step("fetch")
    else:
        st.error("No chess engine found on this computer.")
        st.caption(
            "This app never bundles or auto-downloads an engine itself -- "
            "Stockfish (recommended) and any other UCI-compatible engine "
            "are separate, independently-licensed projects.")
        _engine_install_instructions()
        if st.button("I've installed it -- check again"):
            st.rerun()
        st.divider()
        _render_engine_picker()


def _render_fetch(db_path):
    st.subheader("Step 3 of 5: fetch a few real games")
    cfg = get_config()
    st.markdown(
        f"We'll pull up to **{MAX_FETCH_GAMES}** of your most recent games from "
        f"lichess (`{cfg['player']['name']}`) -- enough to measure real timing "
        "and give you a starter batch to analyze. This does not touch lichess "
        "in any way other than a normal read of your public game history.")
    back_col, fetch_col = st.columns([1, 3])
    with back_col:
        if st.button("Back"):
            _set_step("username")
            st.rerun()
    with fetch_col:
        fetch_clicked = st.button("Fetch my games", type="primary")
    if fetch_clicked:
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
            except requests.exceptions.RequestException:
                st.error("Couldn't reach lichess — check your internet connection and try again.")
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
        with st.spinner("Updating dashboard data..."):
            _refresh_duck_snapshot()
        if st.session_state.get("onboard_returning"):
            _set_step("fetch_done")
        else:
            _set_step("calibrate")


def _render_fetch_chesscom(db_path):
    """Chess.com's additive-only sync step, reached only from _render_status
    (never a first-run path -- lichess's username/engine/calibrate/plan
    steps are the only route into onboarding fresh). Always routes to
    _render_fetch_done afterward, the same shared "done" screen the
    returning-user lichess fetch already uses -- calibration is
    engine-specific, not source-specific, and only ever needs to run once,
    so there's no chess.com equivalent of the calibrate/plan steps at all.
    """
    st.subheader("Fetch new games from chess.com")
    cfg = get_config()
    username = cfg["player"].get("chesscom_username")
    st.markdown(
        f"We'll check for any new games from chess.com (`{username}`) since "
        "the last sync and add them to the analysis queue. This does not "
        "touch chess.com in any way other than a normal read of your "
        "public game history.")
    back_col, fetch_col = st.columns([1, 3])
    with back_col:
        if st.button("Back"):
            _set_step("status")
            st.rerun()
    with fetch_col:
        fetch_clicked = st.button("Fetch my games", type="primary")
    if fetch_clicked:
        with st.spinner("Talking to chess.com..."):
            try:
                sync_chesscom.run(db_path, username, cfg["ingestion"]["queue_strategy"],
                                   cfg["ingestion"]["variant_policy"],
                                   cfg["sync_chesscom"]["request_timeout_seconds"])
            except ValueError as e:
                # list_archive_months() raises this specifically for a 404
                # -- a plain, non-technical message, same reasoning as the
                # lichess HTTPError handling above.
                st.error(str(e))
                return
            except requests.exceptions.RequestException:
                st.error("Couldn't reach chess.com — check your internet connection and try again.")
                return
        conn = get_sqlite_connection(db_path)
        n = conn.execute("SELECT COUNT(*) FROM games WHERE site = 'Chess.com'").fetchone()[0]
        if n == 0:
            st.error(f"No games found for '{username}' -- check the username is correct "
                     "(case-sensitive) and that the account has public games.")
            return
        st.success(f"{n:,} chess.com game(s) in the database.")
        st.session_state["onboard_fetched_count"] = n
        with st.spinner("Updating dashboard data..."):
            _refresh_duck_snapshot()
        _set_step("fetch_done")


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
        _refresh_duck_snapshot()  # the games saved before the error should still show up
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
    status_text.text("Refreshing dashboard data...")
    _refresh_duck_snapshot()
    status_text.success(f"Done -- {completed['games_done']} games analyzed.")
    _set_step("done")


def _render_fetch_done(overview_page):
    n = st.session_state.get("onboard_fetched_count", 0)
    st.success(f"{n:,} new game(s) added to the analysis queue.")
    st.info("Head to **Analysis Jobs** in the sidebar to start an analysis batch.")
    if st.button("Go to dashboard", type="primary"):
        st.switch_page(overview_page)


def _render_done(overview_page):
    st.success("Your starter batch is ready -- accuracy numbers are computed and the "
               "dashboard is up to date.")
    st.info("To run more analysis batches in the future, use **Analysis Jobs** in the sidebar.")
    if st.button("Go to dashboard", type="primary"):
        st.session_state["just_completed_onboarding"] = True
        st.switch_page(overview_page)

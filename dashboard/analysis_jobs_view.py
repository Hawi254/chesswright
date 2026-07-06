"""
Analysis Jobs -- start/stop Stockfish analysis batches, watch live
progress, tune engine/batch settings, and catch up on annotation. Scoped
per the checkpointed design (see BRIEF.md and the design conversation
that preceded this file):

1. Background execution model: a real background thread (job_runner.py),
   not a blocking page like onboarding_view.py's wizard -- this view's
   whole point is being able to navigate elsewhere and come back. The
   status panel below is an `st.fragment(run_every=...)` for exactly that
   reason -- a plain script-level render only updates on user interaction,
   which would defeat "leave this page and the run keeps going."
2. Stop: cooperative, checked between moves (worker.py's stop_event,
   same checkpoint max_duration already used in production).
3. Concurrent-run guard: job_runner.py's in-process slot + joblock.py's
   cross-process PID lock, both checked before a new run is allowed to
   start.
4. Unannotated-game detection: annotate.count_games_awaiting_annotation(),
   not annotate.fetch_games_to_annotate()'s broader idempotent-recompute
   query.
5. Notification: a persistent indicator (this page's own status panel +
   app.py's sidebar block), st.toast() only for one-shot "just finished"
   events -- confirmed live that st.toast() does not persist across
   reruns.
6. Settings: depth/multipv/max_games/max_duration up front, threads/
   hash_mb in a collapsed Advanced expander, same page/form.
7. Navigation: this dedicated page, in app.py's "App" group next to
   Settings -- an ongoing operational concern, not one-time setup.
"""
import streamlit as st

import annotate
import config as config_module
import joblock
import job_runner
from worker import parse_duration
from _common import get_config, get_sqlite_connection, resolve_db_path


def _queue_counts(conn):
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN analysis_status IN ('pending','in_progress') THEN 1 ELSE 0 END),
            SUM(CASE WHEN analysis_status = 'done' THEN 1 ELSE 0 END),
            SUM(CASE WHEN analysis_status = 'failed' THEN 1 ELSE 0 END)
        FROM games
    """).fetchone()
    pending, done, failed = row
    return pending or 0, done or 0, failed or 0


def _render_lock_warning(lock_info):
    started = lock_info.started_at
    if lock_info.alive:
        st.warning(
            f"An analysis run is already in progress outside this app (pid {lock_info.pid}, "
            f"started {started}) -- most likely a `worker.py` run from a terminal. Starting "
            "another one here would compete for CPU against it, not corrupt anything, but "
            "isn't worth doing. Stop that run first, then come back here.")
    else:
        st.info(
            f"A leftover lock from pid {lock_info.pid} (started {started}) was found, but that "
            "process is no longer running -- it likely crashed or was killed without cleaning up "
            "after itself. Safe to clear.")
        if st.button("Clear stale lock"):
            joblock.force_release()
            st.rerun()


@st.fragment(run_every="2s")
def _render_status(db_path, cfg):
    """Polls analysis_runs/games (via job_runner's snapshot + a fresh
    query) every 2s, independent of whether the user is doing anything
    else on the page -- this is the actual mechanism that lets "navigate
    away and come back" work, not just the background thread alone."""
    conn = get_sqlite_connection(db_path)
    state = job_runner.get_state()
    running = job_runner.is_running()
    lock_info = joblock.status()

    pending, done, failed = _queue_counts(conn)
    awaiting_annotation = annotate.count_games_awaiting_annotation(conn)

    cols = st.columns(4)
    cols[0].metric("Waiting for analysis", f"{pending:,}",
                   help="Synced games queued for engine analysis. Start a batch "
                        "below to work through them.")
    cols[1].metric("Analyzed", f"{done:,}",
                   help="Games fully analyzed by the engine.")
    cols[2].metric("Failed", f"{failed:,}",
                   help="Games where analysis hit an error — retried on a later batch.")
    cols[3].metric("Awaiting annotation", f"{awaiting_annotation:,}",
                   help="Analyzed games missing the final bookkeeping step that "
                        "computes accuracy stats and move labels — run it with the "
                        "button below.")

    if running:
        games_done = state.get("games_done", 0)
        st.info(f"Batch running -- {games_done} game(s) analyzed so far this run.")
        if st.button("Stop after current move", help="Cooperative -- finishes the in-progress "
                                                       "move, leaves the game safely resumable."):
            job_runner.stop()
            st.rerun()
    elif state.get("status") == "stopping":
        st.info("Stopping -- waiting for the in-progress move to finish...")
    elif state.get("status") == "error":
        st.error(f"The last run stopped with an error: {state.get('error')}")
    elif state.get("status") == "done":
        # get_state() returns a fresh copy every 2s poll -- mutating it
        # wouldn't dedupe anything against the next poll. run_seq (set
        # once per job_runner.start() call) compared against this
        # session's own session_state is what makes the toast fire
        # exactly once per finished run, not once every 2s forever.
        if st.session_state.get("analysis_jobs_acked_run_seq") != state.get("run_seq"):
            st.toast("Analysis batch finished — see Batch Impact for what changed.")
            st.session_state["analysis_jobs_acked_run_seq"] = state.get("run_seq")
            # Just the id, not a computed delta -- Batch Impact (BRIEF §6u) now
            # owns computing/persisting what a run actually changed, keyed on
            # analysis_runs' own permanent history. This page stays purely
            # operational (start/stop/monitor/settings) and only keeps enough
            # state to link there.
            st.session_state["last_completed_run_id"] = state.get("completed_run_id")

    if lock_info is not None and not running:
        _render_lock_warning(lock_info)

    # Two distinct reasons to show "Run annotation pass now", checked
    # separately since a database can have either without the other:
    # awaiting_annotation is games that have never been annotated at all
    # (narrow signal, see count_games_awaiting_annotation's docstring);
    # motif_backfill_needed is games that WERE annotated, but before motif
    # classification (Pass 4, v0.1.9) existed, so they need the same
    # idempotent run() again even though awaiting_annotation reads 0 for
    # them. Without this second check, a database that only has the
    # backfill problem never shows a way to fix it.
    backfill_needed = annotate.motif_backfill_needed(conn)
    if (awaiting_annotation or backfill_needed) and not running:
        if awaiting_annotation:
            st.info(f"{awaiting_annotation:,} game(s) are analyzed but not yet annotated — "
                    "annotation is the quick final step that turns raw engine numbers "
                    "into accuracy stats and move labels (best/mistake/blunder).")
        else:
            st.info("Some of your analyzed games are missing tactical motif data "
                    "(fork/pin/skewer/etc. classification) because they were analyzed "
                    "before that feature existed.")
        if st.button("Run annotation pass now"):
            with st.spinner("Annotating..."):
                annotate.run(db_path, cfg["annotation"]["mate_score_cap_cp"],
                             cfg["annotation"]["thresholds"],
                             cfg["annotation"]["brilliant_material_threshold_cp"],
                             cfg["annotation"]["puzzle"], cfg["annotation"]["best_move_streak"],
                             game_id=None)
            st.success("Annotation pass complete.")
            st.rerun()

    return running


def render(batch_impact_page=None):
    st.title("Analysis Jobs")

    db_path = resolve_db_path()
    cfg = get_config()

    running = _render_status(db_path, cfg)

    completed_run_id = st.session_state.get("last_completed_run_id")
    if completed_run_id and not running:
        with st.container(border=True):
            st.write(f"Batch #{completed_run_id} finished.")
            if batch_impact_page is not None and st.button("See what changed →"):
                st.switch_page(batch_impact_page)

    st.divider()

    # ---------- Start ----------
    if running:
        st.caption("A batch is already running -- use the Stop button above to end it first.")
    else:
        if st.button("Start analysis batch", type="primary"):
            st.session_state.pop("last_completed_run_id", None)  # clear stale link on new run
            cfg = get_config()  # re-read so any just-saved settings are picked up
            try:
                job_runner.start(
                    db_path, cfg["engine"]["depth"], cfg["engine"]["multipv"],
                    cfg["engine"]["threads"], cfg["engine"]["hash_mb"], cfg["engine"]["pv_max_len"],
                    cfg["engine"]["path"], cfg["worker"]["max_games"],
                    parse_duration(cfg["worker"]["max_duration"]),
                    cfg["worker"]["consecutive_failure_limit"], cfg["worker"]["commit_every_n_moves"])
            except (RuntimeError, joblock.LockHeldError) as e:
                st.error(str(e))
            else:
                st.rerun()

    st.divider()

    # ---------- Settings ----------
    st.subheader("Engine and batch settings")
    with st.form("analysis_job_settings"):
        col1, col2 = st.columns(2)
        depth = col1.number_input("Search depth", min_value=1, max_value=40,
                                  help="How deep the engine looks at every move. Higher = "
                                       "more accurate verdicts but much slower analysis.",
                                   value=cfg["engine"]["depth"])
        multipv = col2.number_input("MultiPV (candidate lines per move)", min_value=1, max_value=10,
                                    help="How many alternative moves the engine evaluates per "
                                         "position — needed for sharpness and missed-tactic "
                                         "detection. 3 is a good default.",
                                     value=cfg["engine"]["multipv"])
        max_games = col1.number_input("Max games this run (0 = no limit)", min_value=0,
                                       value=cfg["worker"]["max_games"] or 0)
        max_duration = col2.text_input("Max duration this run (e.g. 2h, 90m -- blank = no limit)",
                                        value=cfg["worker"]["max_duration"] or "")

        with st.expander("Advanced"):
            acol1, acol2 = st.columns(2)
            threads = acol1.number_input("Engine threads", min_value=1, max_value=64,
                                          value=cfg["engine"]["threads"])
            hash_mb = acol2.number_input("Engine hash table (MB)", min_value=16, max_value=8192,
                                          value=cfg["engine"]["hash_mb"])

        save_clicked = st.form_submit_button("Save settings", disabled=running)

    if save_clicked:
        config_module.set_engine_setting("depth", int(depth))
        config_module.set_engine_setting("multipv", int(multipv))
        config_module.set_engine_setting("threads", int(threads))
        config_module.set_engine_setting("hash_mb", int(hash_mb))
        config_module.set_worker_setting("max_games", int(max_games) if max_games else None)
        config_module.set_worker_setting("max_duration", max_duration.strip() or None)
        st.success("Settings saved.")

    if running:
        st.caption("Settings are read-only while a batch is running -- stop it first to change them.")

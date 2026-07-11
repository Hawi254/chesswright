"""
Settings page -- the bring-your-own Anthropic API key entry point
(BRIEF.md S3). This is the new project's equivalent of the original
project's "set ANTHROPIC_API_KEY and restart" rule, adapted for an
installer who isn't assumed to be comfortable with environment
variables or a terminal at all.
"""
import pathlib
import shutil
import stat

import requests
import streamlit as st

import api_key_store
import config
import db_import
import live_engine
import sync_chesscom
import worker
from _common import resolve_db_path
import components.native_file_picker as native_file_picker


def render():
    st.title("Settings")

    (tab_account, tab_engine, tab_analytics, tab_ingestion, tab_advanced,
     tab_api, tab_pro, tab_support) = st.tabs([
        "Account & Data", "Analysis Engine", "Analytics & Display", "Ingestion",
        "Advanced", "Anthropic API key", "Chesswright Pro", "Support",
    ])

    with tab_account:
        _render_account_data_tab()
    with tab_engine:
        _render_analysis_engine_tab()
    with tab_analytics:
        _render_analytics_display_tab()
    with tab_ingestion:
        _render_ingestion_tab()
    with tab_advanced:
        _render_advanced_tab()
    with tab_api:
        _render_api_key_tab()
    with tab_pro:
        _render_pro_section()
    with tab_support:
        _render_support_section()


def _install_engine_binary(src_path: pathlib.Path, engines_dir: pathlib.Path,
                            validate_fn=None) -> str:
    """Copies src_path into engines_dir, marks it executable, and validates
    it as a real UCI engine (worker.validate_engine_path by default --
    overridable so tests don't need a real engine binary). Returns the
    engine's self-reported name. Raises RuntimeError (from validate_fn) if
    it isn't a working UCI engine -- the partially-installed file is
    removed before re-raising, so a bad pick never lingers in engines_dir."""
    validate_fn = validate_fn or worker.validate_engine_path
    engines_dir.mkdir(parents=True, exist_ok=True)
    dest = engines_dir / src_path.name
    shutil.copy2(src_path, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        return validate_fn(str(dest))
    except RuntimeError:
        dest.unlink(missing_ok=True)
        raise


def _install_engine_upload(uploaded_file, engines_dir: pathlib.Path,
                            validate_fn=None) -> str:
    """Same as _install_engine_binary, for an st.file_uploader result
    instead of a filesystem path (write_bytes instead of copy2)."""
    validate_fn = validate_fn or worker.validate_engine_path
    engines_dir.mkdir(parents=True, exist_ok=True)
    dest = engines_dir / pathlib.Path(uploaded_file.name).name
    dest.write_bytes(uploaded_file.getvalue())
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        return validate_fn(str(dest))
    except RuntimeError:
        dest.unlink(missing_ok=True)
        raise


def _render_api_key_tab():
    st.subheader("Anthropic API key")
    st.caption(
        "Optional. Powers the on-demand 'richer narrative' / commentary "
        "buttons throughout the app (game stories, opening and opponent "
        "commentary). Everything else works without one -- this only "
        "unlocks the Claude-API extras. You pay for your own usage "
        "directly through your own Anthropic account; this app never "
        "sends your key anywhere except Anthropic's API.")
    st.caption(
        "**Shared computers:** if this machine has multiple user accounts, "
        "be aware that without an OS keychain (see the warning below if "
        "one appears after saving) the key is stored in a plain text file "
        "that any other user on this system could read. If this is a "
        "shared machine, consider not configuring a key here, or use a "
        "machine you control exclusively.")

    current_key = api_key_store.get_api_key()
    secure_backend = api_key_store.using_secure_backend()

    if current_key:
        masked = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 12 else "set"
        st.success(f"A key is currently configured ({masked}).")
        if not secure_backend:
            st.warning(
                "No OS-native secure credential store was found on this "
                "system, so your key is stored in a plain text file at "
                "~/.chesswright/api_key.txt instead of your OS keychain. "
                "This is less secure -- anyone with access to your user "
                "account could read that file. This is normal on some "
                "minimal Linux installs; if you'd rather avoid it, install "
                "and run a Secret Service provider (e.g. gnome-keyring) "
                "and re-enter your key here.")
    else:
        st.info("No API key configured yet.")

    with st.form("api_key_form", clear_on_submit=True):
        new_key = st.text_input("Anthropic API key", type="password",
                                 placeholder="sk-ant-...")
        save_clicked = st.form_submit_button("Save key", type="primary")

    if save_clicked:
        if not new_key.strip():
            st.error("Enter a key before saving.")
        else:
            stored_securely = api_key_store.set_api_key(new_key)
            if stored_securely:
                st.success("Key saved to your OS credential store.")
            else:
                st.warning(
                    "Key saved, but no secure OS credential store was "
                    "available -- it's stored in a plain text file "
                    "(~/.chesswright/api_key.txt) instead. See the note "
                    "above for how to switch to secure storage.")
            st.rerun()

    if current_key:
        if st.button("Remove saved key"):
            api_key_store.clear_api_key()
            st.success("Saved key removed.")
            st.rerun()


def _render_analysis_engine_tab():
    st.subheader("Engine location")
    st.caption(
        "The Stockfish (or other UCI-compatible) engine binary used by "
        "both the batch analysis worker and the on-demand probes below. "
        "Auto-detected on first run -- use this if you've since installed "
        "Stockfish somewhere new, or want to switch engines.")

    cfg = config.load_config()
    current_path = cfg["engine"].get("path")
    detected_path = current_path or worker.find_engine_path(None)

    if detected_path:
        st.success(f"Using: `{detected_path}`" +
                   ("" if current_path else " (auto-detected)"))
    else:
        st.error(
            "No chess engine found. Install Stockfish from "
            "[stockfishchess.org/download](https://stockfishchess.org/download/) "
            "or browse for one below.")

    if st.button("Re-detect"):
        found = worker.find_engine_path(None)
        if found:
            config.set_engine_path(found)
            live_engine.get_engine_service.clear()
            st.success(f"Found and saved: `{found}`.")
            st.rerun()
        else:
            st.error("Still couldn't find one automatically.")

    st.warning(
        "Only pick a binary you obtained directly from "
        "[stockfishchess.org/download](https://stockfishchess.org/download/) "
        "or the official release page of another UCI engine. This app "
        "will execute the file you select -- do not pick a file from an "
        "untrusted source.")

    engines_dir = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent / "engines"

    picked_path = native_file_picker.pick(
        "engine", label="Browse for its executable file (native dialog)…",
        key="settings_engine_native_picker")
    if picked_path and picked_path != st.session_state.get(
            "settings_engine_native_picker_applied"):
        st.session_state["settings_engine_native_picker_applied"] = picked_path
        with st.spinner("Checking it speaks UCI..."):
            try:
                engine_name = _install_engine_binary(pathlib.Path(picked_path), engines_dir)
            except RuntimeError as e:
                st.error(str(e))
            else:
                config.set_engine_path(str(engines_dir / pathlib.Path(picked_path).name))
                live_engine.get_engine_service.clear()
                st.success(f"Confirmed and saved: {engine_name}.")
                st.rerun()

    uploaded_engine = st.file_uploader(
        "Or upload its executable file:", key="settings_engine_uploader")
    if uploaded_engine is not None:
        with st.spinner("Checking it speaks UCI..."):
            try:
                engine_name = _install_engine_upload(uploaded_engine, engines_dir)
            except RuntimeError as e:
                st.error(str(e))
            else:
                config.set_engine_path(str(engines_dir / pathlib.Path(uploaded_engine.name).name))
                live_engine.get_engine_service.clear()
                st.success(f"Confirmed and saved: {engine_name}.")
                st.rerun()

    st.divider()
    st.subheader("Live engine settings")
    st.caption(
        "Controls the on-demand Stockfish analysis in the position browser and "
        "game detail panels. The live engine is always paused when the batch "
        "worker is running — these settings only affect interactive probes.")
    ie_cfg = config.load_config().get("interactive_engine", {})
    _ie_defaults = {
        "ie_time_sec":        float(ie_cfg.get("time_sec", 0.5)),
        "ie_depth":           int(ie_cfg.get("depth", 20)),
        "ie_threads":         int(ie_cfg.get("threads", 1)),
        "ie_hash_mb":         int(ie_cfg.get("hash_mb", 32)),
        "ie_store_threshold": int(ie_cfg.get("store_threshold", 20)),
        "ie_use_cloud_eval":  bool(ie_cfg.get("use_lichess_cloud_eval", True)),
    }
    for k, v in _ie_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    with st.form("live_engine_form"):
        col1, col2 = st.columns(2)
        time_sec = col1.number_input(
            "Time limit (s)",
            min_value=0.1, max_value=10.0,
            step=0.1, format="%.1f",
            key="ie_time_sec",
            help="Hard wall-clock cap per position. Always enforced alongside "
                 "the depth limit — whichever is hit first stops the search.")
        depth = col2.number_input(
            "Depth limit",
            min_value=5, max_value=40,
            step=1,
            key="ie_depth",
            help="Maximum search depth. Paired with the time limit — depth "
                 "alone is not a safe limit.")
        threads = col1.number_input(
            "Threads",
            min_value=1, max_value=8,
            step=1,
            key="ie_threads",
            help="Keep at 1 to avoid competing with the batch engine if both "
                 "happen to run on the same machine.")
        hash_mb = col2.number_input(
            "Hash (MB)",
            min_value=16, max_value=1024,
            step=16,
            key="ie_hash_mb",
            help="Stockfish hash table size for interactive probes. Smaller "
                 "than the batch engine's hash to keep the footprint low.")
        store_threshold = col1.number_input(
            "Store threshold (depth)",
            min_value=0, max_value=50,
            step=1,
            key="ie_store_threshold",
            help="Only save the result to position_cache when the actual "
                 "search depth reached this value. Set higher than the depth "
                 "limit above to disable auto-storing entirely.")
        use_cloud_eval = st.checkbox(
            "Use Lichess cloud evaluations when available",
            key="ie_use_cloud_eval",
            help="Before spinning up the local engine on a position lookup, "
                 "try Lichess's free cloud-eval database first (deep evals "
                 "for popular/opening positions, from other players' prior "
                 "analysis). Only the board position (FEN) is sent — no "
                 "account or game data. Falls back to the local engine on a "
                 "miss.")
        save_btn = st.form_submit_button("Save and restart engine", type="primary")

    if save_btn:
        new_settings = {
            "time_sec": round(float(time_sec), 1),
            "depth": int(depth),
            "threads": int(threads),
            "hash_mb": int(hash_mb),
            "store_threshold": int(store_threshold),
            "use_lichess_cloud_eval": bool(use_cloud_eval),
        }
        try:
            config.save_interactive_engine(new_settings)
            live_engine.get_engine_service.clear()
            st.toast("Live engine settings saved.", icon="✅")
        except Exception as e:
            st.error(f"Could not save settings: {e}")

    st.divider()
    st.subheader("Engine Profiles")
    st.caption(
        "Save your current engine speed/depth settings under a name you "
        "choose, and switch between them later -- e.g. 'Laptop' vs. "
        "'Desktop' vs. 'Deep Analysis'. Not the same as Chesswright Pro's "
        "student profiles further down this page, which are separate "
        "databases for different players.")

    profile_names = config.list_engine_profiles()
    col1, col2 = st.columns(2)
    with col1:
        new_profile_name = st.text_input("Save current settings as…",
                                          key="new_engine_profile_name")
        if st.button("Save profile") and new_profile_name.strip():
            config.save_engine_profile(new_profile_name.strip())
            st.success(f"Saved profile '{new_profile_name.strip()}'.")
            st.rerun()
    with col2:
        if profile_names:
            selected_profile = st.selectbox("Saved profiles", profile_names,
                                             key="selected_engine_profile")
            apply_col, delete_col = st.columns(2)
            if apply_col.button("Apply", key="apply_engine_profile"):
                config.apply_engine_profile(selected_profile)
                live_engine.get_engine_service.clear()
                st.success(f"Applied '{selected_profile}'.")
                st.rerun()
            confirm_delete = delete_col.checkbox(
                "Confirm delete", key="confirm_delete_engine_profile")
            if delete_col.button("Delete", key="delete_engine_profile",
                                  disabled=not confirm_delete):
                config.delete_engine_profile(selected_profile)
                st.success(f"Deleted '{selected_profile}'.")
                st.rerun()
        else:
            st.caption("No saved profiles yet.")

    st.divider()
    if st.button("Reset engine settings to defaults", key="reset_engine_defaults"):
        template_path = pathlib.Path(config.__file__).resolve().parent / "config.yaml"
        template_cfg = config.load_config(template_path)
        config.reset_engine_path()
        config.save_interactive_engine(template_cfg["interactive_engine"])
        live_engine.get_engine_service.clear()
        st.success("Engine settings reset to defaults.")
        st.rerun()


def _render_analytics_display_tab():
    st.subheader("Local timezone")
    st.caption(
        "Your local UTC offset, used to show 'time of day' findings "
        "(like the day-of-week × hour win-rate map on Patterns & "
        "Tendencies) in your own local time instead of raw UTC.")
    cfg = config.load_config()
    offset = st.number_input(
        "UTC offset (hours)", min_value=-12, max_value=14, step=1,
        value=int(cfg["analytics"]["utc_offset_hours"]),
        help="E.g. -5 for US Eastern Standard Time, +1 for Central "
             "European Time.")
    if st.button("Save timezone"):
        config.set_analytics_setting("utc_offset_hours", int(offset))
        st.cache_data.clear()
        st.toast("Timezone saved.", icon="✅")
        st.rerun()

    st.divider()
    st.subheader("Confidence threshold")
    st.caption(
        "The minimum sample size (games/positions) a stat needs before "
        "it's shown as trustworthy instead of flagged '(small sample)' "
        "across Insights, Openings, Matchups, and other pages. One shared "
        "threshold, not a per-page setting.")
    min_sample_size = st.number_input(
        "Minimum sample size", min_value=1, max_value=100, step=1,
        value=int(cfg["analytics"]["min_sample_size"]),
        help="Groups below this many analyzed games are shown but marked "
             "as a small sample, rather than hidden.")
    if st.button("Save confidence threshold"):
        config.set_analytics_setting("min_sample_size", int(min_sample_size))
        st.cache_data.clear()
        st.toast("Confidence threshold saved.", icon="✅")
        st.rerun()

    st.divider()
    if st.button("Reset analytics & display settings to defaults", key="reset_analytics_defaults"):
        template_path = pathlib.Path(config.__file__).resolve().parent / "config.yaml"
        template_cfg = config.load_config(template_path)
        config.set_analytics_setting("utc_offset_hours", template_cfg["analytics"]["utc_offset_hours"])
        config.set_analytics_setting("min_sample_size", template_cfg["analytics"]["min_sample_size"])
        st.cache_data.clear()
        st.success("Analytics & Display settings reset to defaults.")
        st.rerun()


def _render_ingestion_tab():
    st.subheader("New game ingestion")
    st.caption(
        "Controls how future syncs (lichess/chess.com) and the analysis "
        "worker treat newly-fetched games. Doesn't affect games already "
        "in your database.")
    cfg = config.load_config()

    variant_options = ["skip", "include"]
    variant_policy = st.selectbox(
        "Non-standard variants (Chess960, Atomic, ...)",
        options=variant_options,
        index=variant_options.index(cfg["ingestion"]["variant_policy"]),
        help="'skip' (default) ignores non-Standard-chess games entirely -- "
             "safe, since the batch engine assumes normal rules. Only "
             "choose 'include' if you plan to analyze those games with a "
             "variant-aware engine separately.")

    queue_options = ["interleaved_by_year", "chronological", "reverse_chronological"]
    queue_strategy = st.selectbox(
        "Analysis queue order",
        options=queue_options,
        index=queue_options.index(cfg["ingestion"]["queue_strategy"]),
        help="Only takes effect for a manual full re-import (running ingest.py "
             "directly) -- regular syncs from this app always place newly-fetched "
             "games at the front of the queue regardless of this setting. "
             "'interleaved_by_year' (default) samples across your whole history "
             "early instead of only your oldest or newest games.")

    if st.button("Save ingestion settings"):
        config.set_ingestion_setting("variant_policy", variant_policy)
        config.set_ingestion_setting("queue_strategy", queue_strategy)
        st.toast("Ingestion settings saved.", icon="✅")
        st.rerun()

    st.divider()
    if st.button("Reset ingestion settings to defaults", key="reset_ingestion_defaults"):
        template_path = pathlib.Path(config.__file__).resolve().parent / "config.yaml"
        template_cfg = config.load_config(template_path)
        config.set_ingestion_setting("variant_policy", template_cfg["ingestion"]["variant_policy"])
        config.set_ingestion_setting("queue_strategy", template_cfg["ingestion"]["queue_strategy"])
        st.success("Ingestion settings reset to defaults.")
        st.rerun()


def _render_advanced_tab():
    with st.expander("Advanced settings", expanded=False):
        st.caption(
            "Lower-level tuning knobs -- most of which config.yaml itself "
            "documents as safe defaults not worth changing. Shown here so "
            "they're not YAML-only, without pretending they're as commonly "
            "needed as the settings on the other tabs.")
        cfg = config.load_config()

        st.markdown("**Batch engine**")
        pv_max_len = st.number_input(
            "Stored line length (plies)", min_value=1, max_value=60, step=1,
            value=int(cfg["engine"]["pv_max_len"]), key="adv_pv_max_len",
            help="Plies of each line's continuation to store (storage vs. detail).")
        reuse_evals = st.checkbox(
            "Reuse a prior batch result for an exact-FEN repeat position",
            value=bool(cfg["engine"]["reuse_evals"]), key="adv_reuse_evals",
            help="Instead of re-running Stockfish. Unchecking restores the "
                 "old always-re-analyze behavior.")

        st.markdown("**Batch worker**")
        consecutive_failure_limit = st.number_input(
            "Stop after this many consecutive game failures", min_value=1,
            max_value=100, step=1,
            value=int(cfg["worker"]["consecutive_failure_limit"]),
            key="adv_consecutive_failure_limit",
            help="Stops the batch rather than silently failing the whole queue.")
        commit_every_n_moves = st.number_input(
            "Commit every N moves", min_value=1, max_value=100, step=1,
            value=int(cfg["worker"]["commit_every_n_moves"]),
            key="adv_commit_every_n_moves",
            help="1 (default) is safest -- a crash loses at most the "
                 "in-flight position. Not recommended to change.")

        st.markdown("**Ingestion queue fairness**")
        berserk_max_clock_fraction = st.number_input(
            "Berserk clock fraction", min_value=0.0, max_value=1.0, step=0.05,
            format="%.2f", value=float(cfg["ingestion"]["berserk_max_clock_fraction"]),
            key="adv_berserk_max_clock_fraction",
            help="A color is flagged berserk when its first clock reading "
                 "is at or below this fraction of the base time.")
        backlog_quota = st.number_input(
            "Backlog quota", min_value=0.0, max_value=1.0, step=0.05,
            format="%.2f", value=float(cfg["ingestion"]["backlog_quota"]),
            key="adv_backlog_quota",
            help="Minimum share of recently-analyzed games that must come "
                 "from the historical backlog, even while new synced games "
                 "are pending. 0 = recent games always win; 1 = backlog only.")
        backlog_quota_window = st.number_input(
            "Backlog quota window (games)", min_value=1, max_value=1000, step=1,
            value=int(cfg["ingestion"]["backlog_quota_window"]),
            key="adv_backlog_quota_window",
            help="How many of the most recently analyzed games the backlog "
                 "quota above looks at.")

        st.markdown("**Sync timeouts**")
        sync_timeout = st.number_input(
            "Lichess sync request timeout (s)", min_value=1, max_value=300, step=1,
            value=int(cfg["sync"]["request_timeout_seconds"]), key="adv_sync_timeout")
        sync_chesscom_timeout = st.number_input(
            "Chess.com sync request timeout (s)", min_value=1, max_value=300, step=1,
            value=int(cfg["sync_chesscom"]["request_timeout_seconds"]),
            key="adv_sync_chesscom_timeout")

        if st.button("Save advanced settings"):
            config.set_engine_setting("pv_max_len", int(pv_max_len))
            config.set_engine_setting("reuse_evals", bool(reuse_evals))
            config.set_worker_setting("consecutive_failure_limit", int(consecutive_failure_limit))
            config.set_worker_setting("commit_every_n_moves", int(commit_every_n_moves))
            config.set_ingestion_setting("berserk_max_clock_fraction", round(float(berserk_max_clock_fraction), 2))
            config.set_ingestion_setting("backlog_quota", round(float(backlog_quota), 2))
            config.set_ingestion_setting("backlog_quota_window", int(backlog_quota_window))
            config.set_sync_setting("request_timeout_seconds", int(sync_timeout))
            config.set_sync_chesscom_setting("request_timeout_seconds", int(sync_chesscom_timeout))
            st.toast("Advanced settings saved.", icon="✅")
            st.rerun()


def _render_account_data_tab():
    st.subheader("Import an existing database")
    st.caption(
        "For returning users: point at a chesswright-compatible database "
        "file already on this computer (e.g. from a previous install, or "
        "built by running the original open backend standalone) instead "
        "of starting fresh through the onboarding wizard. The file is "
        "copied into this app's own data directory -- the original file is "
        "never modified or referenced afterward.")

    pending_path = st.session_state.get("import_pending_path")

    if not pending_path:
        col1, col2 = st.columns([5, 1])
        # Rendered (and its session_state applied) before the text_input
        # below is instantiated -- Streamlit raises if a widget's key is
        # written to AFTER that widget exists this run, confirmed live.
        # col2 still lands visually on the right regardless of this code
        # order, since column position comes from the column object, not
        # execution order.
        with col2:
            # Real native OS file dialog when running in the packaged
            # desktop app; renders nothing in the plain `streamlit run`
            # dev workflow, where the text input below is the only way
            # in -- see components/native_file_picker for the mechanism.
            st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
            picked = native_file_picker.pick("database", key="import_native_picker")
        # A component's return value persists across reruns until the JS
        # sends a new one -- guard against reapplying the same pick on
        # every later rerun, which would otherwise clobber anything the
        # user typed into the field afterward.
        if picked and picked != st.session_state.get("import_native_picker_applied"):
            st.session_state["import_native_picker_applied"] = picked
            st.session_state["import_path_input"] = picked
        with col1:
            src = st.text_input("Path to the database file on this computer",
                                 placeholder="/home/you/some-folder/chess.db",
                                 key="import_path_input")
        if st.button("Import"):
            try:
                dest_dir = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent
                imported_path = db_import.import_database(pathlib.Path(src.strip()), dest_dir)
            except db_import.DatabaseImportError as e:
                st.error(str(e))
            else:
                st.session_state["import_pending_path"] = str(imported_path)
                st.session_state["import_suggested_username"] = \
                    db_import.suggest_player_name(imported_path) or ""
                st.rerun()
    else:
        st.success(f"Imported and migrated: `{pending_path}`.")
        suggested = st.session_state.get("import_suggested_username", "")
        st.caption(
            "Confirm whose account this database belongs to -- the most "
            "frequently-appearing username was pre-filled below, but this "
            "isn't auto-detected with certainty, so please check it before "
            "continuing.")
        username = st.text_input("Lichess username for this database", value=suggested)
        col1, col2 = st.columns(2)
        if col1.button("Use this database", type="primary", disabled=not username.strip()):
            config.set_database_path(pending_path)
            config.set_player_name(username.strip())
            del st.session_state["import_pending_path"]
            st.session_state.pop("import_suggested_username", None)
            st.cache_resource.clear()
            st.success("Switched to the imported database.")
            st.rerun()
        if col2.button("Cancel"):
            pathlib.Path(pending_path).unlink(missing_ok=True)
            del st.session_state["import_pending_path"]
            st.session_state.pop("import_suggested_username", None)
            st.rerun()

    st.divider()
    _render_chesscom_section()


def _render_chesscom_section():
    """Additive-only chess.com sync (see BRIEF.md's chess.com integration
    scope note): lichess stays the required first-run identity via the
    onboarding wizard; this is where a SECOND, optional source gets
    connected for anyone who also plays on chess.com. Games from both
    platforms coexist in the same database with no conflict -- games.site
    already discriminates them ('Chess.com' vs a lichess.org URL), so
    nothing here needs its own database or profile."""
    st.subheader("Chess.com account (optional)")
    st.caption(
        "Connect a chess.com account to also pull those games into this "
        "same database, alongside your lichess history. Fully optional -- "
        "everything else in the app works with lichess alone.")

    cfg = config.load_config()
    current_username = cfg["player"].get("chesscom_username")

    if current_username:
        st.success(f"Connected: **{current_username}**")
        col1, col2 = st.columns(2)
        if col1.button("Sync now", key="chesscom_sync_now"):
            _run_chesscom_sync(current_username)
        if col2.button("Disconnect", key="chesscom_disconnect"):
            config.set_chesscom_username(None)
            st.success("Disconnected. Games already synced are untouched.")
            st.rerun()
    else:
        with st.form("chesscom_connect_form", clear_on_submit=True):
            new_username = st.text_input(
                "Chess.com username",
                placeholder="exactly as it appears in your profile URL")
            connect_clicked = st.form_submit_button("Connect", type="primary")
        if connect_clicked:
            if not new_username.strip():
                st.error("Enter a username before connecting.")
            else:
                config.set_chesscom_username(new_username.strip())
                st.rerun()


def _run_chesscom_sync(username):
    """Same error-handling shape as onboarding_view._render_fetch's lichess
    sync -- chess.com's PubAPI returns the same class of errors (404 for
    an unknown username, connectivity failures), just from a different
    module (sync_chesscom, not sync)."""
    cfg = config.load_config()
    db_path = resolve_db_path()
    with st.spinner("Talking to chess.com..."):
        try:
            sync_chesscom.run(db_path, username, cfg["ingestion"]["queue_strategy"],
                               cfg["ingestion"]["variant_policy"],
                               cfg["sync_chesscom"]["request_timeout_seconds"])
        except ValueError as e:
            # list_archive_months() raises this specifically for a 404 --
            # a plain, non-technical message rather than str(e) on a raw
            # HTTPError (same reasoning as the lichess onboarding flow).
            st.error(str(e))
            return
        except requests.exceptions.RequestException:
            st.error("Couldn't reach chess.com — check your internet connection and try again.")
            return
    st.success("Sync complete. Head to **Analysis Jobs** in the sidebar to analyze any new games.")


def _render_pro_section():
    st.subheader("Chesswright Pro")
    try:
        from chesswright_pro import license as _lic  # type: ignore[import]
    except ImportError:
        st.info(
            "**Coach Mode** is available in Chesswright Pro.\n\n"
            "Pro adds student profile management — analyse any lichess player's "
            "games in an isolated database, switch between profiles without "
            "losing your own analysis, and generate per-game and tournament-prep "
            "reports.\n\n"
            "Purchase at [chesswright.gumroad.com](https://chesswright.gumroad.com) "
            "then install the Pro package and enter your license key here."
        )
        return

    # Pro is installed -- show license management UI
    key = _lic.get_license_key()
    if key:
        masked = f"{key[:8]}...{key[-4:]}" if len(key) > 14 else "set"
        info = _lic.get_license_info()
        email_hint = f" · {info['purchase_email']}" if info and info.get("purchase_email") else ""
        st.success(f"Pro license active ({masked}{email_hint}).")
        if st.button("Deactivate license"):
            _lic.deactivate()
            st.success("License removed. Pro features will be unavailable until re-activated.")
            st.rerun()
    else:
        st.info("Pro is installed but no license key has been activated.")
        with st.form("pro_license_form", clear_on_submit=True):
            new_key = st.text_input("License key", type="password",
                                     placeholder="Paste your Chesswright Pro key…")
            activate_clicked = st.form_submit_button("Activate", type="primary")
        if activate_clicked:
            if not new_key.strip():
                st.error("Enter a key before activating.")
            else:
                ok, msg = _lic.activate(new_key.strip())
                if ok:
                    st.success(msg + " Reload the app to unlock Pro pages.")
                    st.rerun()
                else:
                    st.error(msg)


def _render_support_section():
    st.subheader("Support this project")
    st.caption(
        "The core app is free and stays free — this isn't a paywall. If "
        "you'd like to support ongoing development anyway: "
        "[GitHub Sponsors](https://github.com/sponsors/Hawi254) · "
        "[Open Collective](https://opencollective.com/chesswright).")

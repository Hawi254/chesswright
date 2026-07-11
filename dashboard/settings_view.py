"""
Settings page -- the bring-your-own Anthropic API key entry point
(BRIEF.md S3). This is the new project's equivalent of the original
project's "set ANTHROPIC_API_KEY and restart" rule, adapted for an
installer who isn't assumed to be comfortable with environment
variables or a terminal at all.
"""
import pathlib

import requests
import streamlit as st

import api_key_store
import config
import db_import
import live_engine
import sync_chesscom
from _common import resolve_db_path
import components.native_file_picker as native_file_picker


def render():
    st.title("Settings")

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

    st.divider()
    st.subheader("Live engine settings")
    st.caption(
        "Controls the on-demand Stockfish analysis in the position browser and "
        "game detail panels. The live engine is always paused when the batch "
        "worker is running — these settings only affect interactive probes.")
    ie_cfg = config.load_config().get("interactive_engine", {})
    # Seed session_state from config on the very first render so explicit
    # keys below initialise correctly, but don't overwrite values the user
    # has already submitted (session_state persists across page navigation).
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

    st.divider()
    _render_pro_section()

    st.divider()
    _render_support_section()


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

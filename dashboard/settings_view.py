"""
Settings page -- the bring-your-own Anthropic API key entry point
(BRIEF.md S3). This is the new project's equivalent of the original
project's "set ANTHROPIC_API_KEY and restart" rule, adapted for an
installer who isn't assumed to be comfortable with environment
variables or a terminal at all.
"""
import pathlib

import streamlit as st

import api_key_store
import config
import db_import
import live_engine


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
    with st.form("live_engine_form"):
        col1, col2 = st.columns(2)
        time_sec = col1.number_input(
            "Time limit (s)",
            min_value=0.1, max_value=10.0,
            value=float(ie_cfg.get("time_sec", 0.5)),
            step=0.1, format="%.1f",
            help="Hard wall-clock cap per position. Always enforced alongside "
                 "the depth limit — whichever is hit first stops the search.")
        depth = col2.number_input(
            "Depth limit",
            min_value=5, max_value=40,
            value=int(ie_cfg.get("depth", 20)),
            step=1,
            help="Maximum search depth. Paired with the time limit — depth "
                 "alone is not a safe limit.")
        threads = col1.number_input(
            "Threads",
            min_value=1, max_value=8,
            value=int(ie_cfg.get("threads", 1)),
            step=1,
            help="Keep at 1 to avoid competing with the batch engine if both "
                 "happen to run on the same machine.")
        hash_mb = col2.number_input(
            "Hash (MB)",
            min_value=16, max_value=1024,
            value=int(ie_cfg.get("hash_mb", 32)),
            step=16,
            help="Stockfish hash table size for interactive probes. Smaller "
                 "than the batch engine's hash to keep the footprint low.")
        store_threshold = col1.number_input(
            "Store threshold (depth)",
            min_value=0, max_value=50,
            value=int(ie_cfg.get("store_threshold", 20)),
            step=1,
            help="Only save the result to position_cache when the actual "
                 "search depth reached this value. Set higher than the depth "
                 "limit above to disable auto-storing entirely.")
        save_btn = st.form_submit_button("Save and restart engine", type="primary")

    if save_btn:
        new_settings = {
            "time_sec": round(float(time_sec), 1),
            "depth": int(depth),
            "threads": int(threads),
            "hash_mb": int(hash_mb),
            "store_threshold": int(store_threshold),
        }
        try:
            config.save_interactive_engine(new_settings)
            live_engine.get_engine_service.clear()
            st.success("Settings saved. The live engine will restart with "
                        "new settings on next use.")
        except Exception as e:
            st.error(f"Failed to save settings: {e}")
        st.rerun()

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
        src = st.text_input("Path to the database file on this computer",
                             placeholder="/home/you/some-folder/chess.db")
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
